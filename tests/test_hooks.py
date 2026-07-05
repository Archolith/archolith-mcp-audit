from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _hook_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return env


def test_standalone_hook_sanitizes_session_id(tmp_path) -> None:
    hook = Path("archolith_mcp_audit/hook_observer_standalone.py")
    proc = subprocess.run(
        [sys.executable, str(hook), "../escape"],
        input=json.dumps({"tool_name": "Read", "tool_result": "ok"}),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=_hook_env(tmp_path),
    )

    assert proc.returncode == 0
    assert json.loads(proc.stdout)["continue"] is True
    assert (tmp_path / ".archolith" / "sessions" / "__escape.jsonl").exists()
    assert not (tmp_path / ".archolith" / "escape.jsonl").exists()


def test_standalone_hook_uses_payload_session_id(tmp_path) -> None:
    """With no CLI arg/env, the session_id is taken from the payload so each
    session lands in its own file instead of collapsing into 'current'."""
    hook = Path("archolith_mcp_audit/hook_observer_standalone.py")
    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(
            {"session_id": "sess-abc", "tool_name": "Read", "tool_result": "ok"}
        ),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=_hook_env(tmp_path),
    )

    assert proc.returncode == 0
    session_file = tmp_path / ".archolith" / "sessions" / "sess-abc.jsonl"
    assert session_file.exists()
    assert not (tmp_path / ".archolith" / "sessions" / "current.jsonl").exists()
    record = json.loads(session_file.read_text(encoding="utf-8").splitlines()[0])
    assert record["session_id"] == "sess-abc"
    assert record["filter_active"] is False


def test_codex_hook_sanitizes_session_id(tmp_path) -> None:
    hook = Path("archolith_mcp_audit/hook_observer_codex.py")
    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps({"session_id": "..\\escape", "tool_name": "Read", "tool_result": "ok"}),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=_hook_env(tmp_path),
    )

    assert proc.returncode == 0
    assert json.loads(proc.stdout)["continue"] is True
    assert (tmp_path / ".archolith" / "sessions" / "__escape.jsonl").exists()


def test_session_start_hook_sanitizes_session_id(tmp_path) -> None:
    hook = Path("archolith_mcp_audit/hook_session_start.py")
    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps({"session_id": "../escape", "cwd": str(tmp_path / "project")}),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=_hook_env(tmp_path),
    )

    assert proc.returncode == 0
    assert json.loads(proc.stdout)["continue"] is True
    assert (tmp_path / ".archolith" / "sessions" / "__escape.name").exists()
    assert (tmp_path / ".archolith" / "sessions" / "__escape.jsonl").exists()
