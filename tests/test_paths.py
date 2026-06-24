from __future__ import annotations

from archolith_mcp_audit._paths import atomic_append_jsonl, atomic_write_text, safe_session_path, sanitize_session_id


def test_sanitize_session_id_blocks_path_traversal() -> None:
    assert sanitize_session_id("../outside") == "__outside"
    assert sanitize_session_id("nested\\outside") == "nested_outside"
    assert sanitize_session_id("\x00\n") == "default"


def test_safe_session_path_stays_under_sessions_dir(tmp_path) -> None:
    path = safe_session_path(tmp_path, "../outside")

    assert path.parent == tmp_path.resolve()
    assert path.name == "__outside.jsonl"


def test_atomic_append_jsonl_writes_single_lines(tmp_path) -> None:
    path = tmp_path / "session.jsonl"

    atomic_append_jsonl(path, '{"a":1}')
    atomic_append_jsonl(path, '{"b":2}\n')

    assert path.read_text(encoding="utf-8") == '{"a":1}\n{"b":2}\n'


def test_atomic_write_text_replaces_file(tmp_path) -> None:
    path = tmp_path / "session.name"

    atomic_write_text(path, "first")
    atomic_write_text(path, "second")

    assert path.read_text(encoding="utf-8") == "second"
