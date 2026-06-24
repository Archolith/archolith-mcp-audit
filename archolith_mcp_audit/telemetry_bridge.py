"""Telemetry bridge — connects audit accumulator to external telemetry sources.

Provides a uniform interface for feeding tool result observations into the
LiveAccumulator from multiple telemetry backends:

  1. archolith-filter FilterTelemetryStore — the primary in-session telemetry source
     when archolith-filter is installed and the filter pipeline is active.
  2. File-based telemetry — reads accumulated observations from a JSONL
     file written by an external process (e.g., a hook observer).
  3. Direct push — programmatic injection of observations from a hook
     observer or other in-process callback.

The bridge is passive: it reads and forwards, it does NOT modify or
intercept MCP traffic.

Usage:
    from archolith_mcp_audit.telemetry_bridge import TelemetryBridge

    bridge = TelemetryBridge(accumulator=my_accumulator)
    bridge.connect_filter()       # connect to archolith-filter telemetry store
    bridge.connect_file(path)     # connect to file-based telemetry
    bridge.push(tool_name, raw, filtered)  # direct push
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from archolith_mcp_audit.accumulator import LiveAccumulator

log = logging.getLogger(__name__)

__all__ = [
    "TelemetrySource",
    "TelemetryEntry",
    "FilterTelemetrySource",
    "RtkTelemetrySource",  # backward compat alias
    "FileTelemetrySource",
    "InMemoryTelemetrySource",
    "TelemetryBridge",
    "write_telemetry_entry",
]


class TelemetrySource(Protocol):
    """Protocol for telemetry sources that can feed observations."""

    def pull(self) -> list[TelemetryEntry]:
        """Pull new observations since last check."""
        ...

    def is_available(self) -> bool:
        """Check if this telemetry source is available."""
        ...


@dataclass
class TelemetryEntry:
    """A single telemetry observation from an external source."""

    tool_name: str
    raw_chars: int
    filtered_chars: int = 0
    timestamp: float = 0.0
    session_id: str = ""
    metadata: dict = field(default_factory=dict)


class FilterTelemetrySource:
    """Telemetry source backed by archolith-filter FilterTelemetryStore.

    Reads from the archolith-filter telemetry store when available.
    Gracefully degrades when archolith-filter is not installed.
    """

    def __init__(self) -> None:
        self._store: object | None = None
        self._last_index: int = 0
        self._available: bool = False
        self._try_connect()

    def _try_connect(self) -> None:
        try:
            # Use the module-level singleton accessor, NOT the FilterTelemetryStore
            # constructor. The constructor returns a fresh, empty store; the
            # proxy/filter pipeline records into the singleton, so reading a new
            # instance would always report zero.
            from archolith_filter.telemetry import get_filter_telemetry_store
            self._store = get_filter_telemetry_store()
            self._available = True
            log.info("Connected to archolith-filter FilterTelemetryStore")
        except ImportError:
            log.debug("archolith-filter not installed, telemetry unavailable")
            self._available = False
        except Exception as e:
            log.warning("Failed to connect to archolith-filter FilterTelemetryStore: %s", e)
            self._available = False

    def is_available(self) -> bool:
        return self._available

    def pull(self) -> list[TelemetryEntry]:
        if not self._available or self._store is None:
            return []

        entries: list[TelemetryEntry] = []

        try:
            # archolith-filter's FilterTelemetryStore exposes its records via the
            # `entries` property. Prefer it; fall back to `records` / get_all()
            # for other store shapes (kept for backward compatibility).
            records = getattr(self._store, "entries", None)
            if records is None:
                records = getattr(self._store, "records", None)
            if records is None:
                get_all = getattr(self._store, "get_all", None)
                if get_all is not None:
                    records = get_all()

            if records is None:
                return []

            if isinstance(records, list):
                new_records = records[self._last_index:]
                self._last_index = len(records)
            else:
                new_records = list(records)
                self._last_index = len(new_records)

            warned_fallback = {"tool_name": False, "raw_chars": False, "filtered_chars": False}

            for rec in new_records:
                tool_name = getattr(rec, "tool_name", None)
                if tool_name is None:
                    tool_name = getattr(rec, "tool", "unknown")
                    if not warned_fallback["tool_name"]:
                        log.warning(
                            "archolith-filter record missing 'tool_name', falling back to 'tool': '%s'",
                            tool_name,
                        )
                        warned_fallback["tool_name"] = True

                raw_chars = getattr(rec, "raw_chars", None)
                if raw_chars is None:
                    raw_chars = getattr(rec, "raw_tokens", 0)
                    if not warned_fallback["raw_chars"]:
                        log.warning(
                            "archolith-filter record missing 'raw_chars', falling back to 'raw_tokens': %s",
                            raw_chars,
                        )
                        warned_fallback["raw_chars"] = True

                filtered_chars = getattr(rec, "filtered_chars", None)
                if filtered_chars is None:
                    filtered_chars = getattr(rec, "filtered_tokens", 0)
                    if not warned_fallback["filtered_chars"]:
                        log.warning(
                            "archolith-filter record missing 'filtered_chars', falling back to 'filtered_tokens': %s",
                            filtered_chars,
                        )
                        warned_fallback["filtered_chars"] = True

                timestamp = getattr(rec, "timestamp", 0.0)

                entries.append(TelemetryEntry(
                    tool_name=tool_name,
                    raw_chars=raw_chars,
                    filtered_chars=filtered_chars,
                    timestamp=timestamp,
                ))
        except Exception as e:
            log.warning("Error reading from archolith-filter telemetry store: %s", e)

        return entries


# Backward compatibility alias
RtkTelemetrySource = FilterTelemetrySource


class FileTelemetrySource:
    """Telemetry source backed by a JSONL file.

    Each line is a JSON object with: tool_name, raw_chars, filtered_chars,
    and optional timestamp, session_id, metadata.

    Tracks file position to only read new entries on each pull.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file_pos: int = 0
        self._available: bool = path.exists()
        if not self._available:
            log.debug("Telemetry file not found: %s", path)

    def is_available(self) -> bool:
        if not self.path.exists():
            return False
        return True

    def pull(self) -> list[TelemetryEntry]:
        if not self.path.exists():
            return []

        entries: list[TelemetryEntry] = []

        try:
            with open(self.path, encoding="utf-8") as f:
                # Detect log rotation: if the file shrank since last read,
                # a new file was written to the same path. Reset position.
                f.seek(0, 2)
                if f.tell() < self._file_pos:
                    log.info("Telemetry file rotated, resetting read position")
                    self._file_pos = 0
                f.seek(self._file_pos)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        log.warning("Invalid JSON in telemetry file: %s", line[:100])
                        continue

                    # Prefer token counts when available (tiktoken-measured).
                    # Fall back to raw char counts for older/fallback entries.
                    raw = obj.get("raw_tokens") or obj.get("raw_chars", 0)
                    filtered = obj.get("filtered_tokens") or obj.get("filtered_chars", 0)

                    # Pre-passthrough entries (before the hook wrote filtered_chars=raw_chars)
                    # had filtered_chars=0, meaning "no filter data" — not "compressed to zero".
                    # Treat as passthrough so stale file entries don't produce false savings.
                    if filtered == 0 and raw > 0 and not obj.get("raw_tokens"):
                        filtered = raw

                    entries.append(TelemetryEntry(
                        tool_name=obj.get("tool_name", "unknown"),
                        raw_chars=raw,
                        filtered_chars=filtered,
                        timestamp=obj.get("timestamp", 0.0),
                        session_id=obj.get("session_id", ""),
                        metadata={
                            **obj.get("metadata", {}),
                            "token_based": bool(obj.get("raw_tokens")),
                            "tiktoken_used": obj.get("tiktoken_used", False),
                        },
                    ))
                self._file_pos = f.tell()
        except OSError as e:
            log.warning("Error reading telemetry file %s: %s", self.path, e)

        return entries


class InMemoryTelemetrySource:
    """In-memory telemetry source for direct programmatic push.

    Used by hook observers and other in-process callbacks that want
    to feed observations into the bridge without going through a file
    or external store.
    """

    def __init__(self) -> None:
        self._entries: list[TelemetryEntry] = []
        self._available: bool = True

    def is_available(self) -> bool:
        return self._available

    def add(self, entry: TelemetryEntry) -> None:
        self._entries.append(entry)

    def add_observation(
        self,
        tool_name: str,
        raw_chars: int,
        filtered_chars: int = 0,
        session_id: str = "",
    ) -> None:
        self._entries.append(TelemetryEntry(
            tool_name=tool_name,
            raw_chars=raw_chars,
            filtered_chars=filtered_chars,
            timestamp=time.time(),
            session_id=session_id,
        ))

    def pull(self) -> list[TelemetryEntry]:
        entries = self._entries[:]
        self._entries.clear()
        return entries


class TelemetryBridge:
    """Bridge that connects telemetry sources to the LiveAccumulator.

    Manages multiple telemetry sources and forwards observations to
    the accumulator. Provides a single sync() call that pulls from
    all connected sources.

    Usage:
        bridge = TelemetryBridge(accumulator=acc)
        bridge.connect_filter()
        bridge.connect_file(Path("/tmp/telemetry.jsonl"))
        bridge.add_source(InMemoryTelemetrySource())

        # Periodically sync (e.g., before each MCP tool call)
        bridge.sync()
    """

    def __init__(self, accumulator: LiveAccumulator) -> None:
        self.accumulator = accumulator
        self.sources: list[TelemetrySource] = []
        self._total_synced: int = 0

    def connect_filter(self) -> bool:
        source = FilterTelemetrySource()
        if source.is_available():
            self.sources.append(source)
            return True
        return False

    # Backward compatibility alias
    connect_rtk = connect_filter

    def connect_file(self, path: Path) -> bool:
        source = FileTelemetrySource(path)
        if source.is_available():
            self.sources.append(source)
            return True
        return False

    def add_source(self, source: TelemetrySource) -> None:
        self.sources.append(source)

    def push(
        self,
        tool_name: str,
        raw_chars: int,
        filtered_chars: int = 0,
        session_id: str = "",
    ) -> None:
        """Directly push an observation to the accumulator.

        Bypasses all sources and writes directly. Useful for
        hook observers that want immediate, synchronous observation.
        """
        self.accumulator.observe(tool_name, raw_chars, filtered_chars)
        self._total_synced += 1

    def sync(self) -> int:
        """Pull new observations from all connected sources.

        Returns the number of new observations synced.
        """
        count = 0

        for source in self.sources:
            if not source.is_available():
                continue
            try:
                entries = source.pull()
                for entry in entries:
                    self.accumulator.observe(
                        entry.tool_name,
                        entry.raw_chars,
                        entry.filtered_chars,
                    )
                    count += 1
            except Exception as e:
                log.warning("Error syncing from telemetry source: %s", e)

        self._total_synced += count
        return count

    @property
    def total_synced(self) -> int:
        return self._total_synced

    def source_count(self) -> int:
        return len(self.sources)

    def active_source_count(self) -> int:
        return sum(1 for s in self.sources if s.is_available())


def write_telemetry_entry(
    path: Path,
    tool_name: str,
    raw_chars: int,
    filtered_chars: int = 0,
    session_id: str = "",
    metadata: dict | None = None,
) -> None:
    """Append a telemetry entry to a JSONL file.

    Utility for hook observers and external processes that want to
    write observations to a file that can be read by FileTelemetrySource.
    """
    entry = {
        "tool_name": tool_name,
        "raw_chars": raw_chars,
        "filtered_chars": filtered_chars,
        "timestamp": time.time(),
        "session_id": session_id,
    }
    if metadata:
        entry["metadata"] = metadata

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
