from __future__ import annotations

import os
from pathlib import Path

from archolith_mcp_audit import bootstrap


def test_ensure_runtime_installs_once_per_requirements_hash(tmp_path, monkeypatch) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    requirements = plugin_root / "requirements.txt"
    requirements.write_text("fastmcp>=0.4\n", encoding="utf-8")

    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)

    def fake_create(self, runtime: Path) -> None:  # noqa: ANN001
        scripts_dir = runtime / ("Scripts" if os.name == "nt" else "bin")
        scripts_dir.mkdir(parents=True, exist_ok=True)
        python = scripts_dir / ("python.exe" if os.name == "nt" else "python")
        python.write_text("# fake python\n", encoding="utf-8")

    installs: list[tuple[Path, Path]] = []
    monkeypatch.setattr(bootstrap.venv.EnvBuilder, "create", fake_create)
    monkeypatch.setattr(bootstrap, "_run_pip", lambda python, req: installs.append((python, req)))

    python = bootstrap.ensure_runtime(agent="claude", plugin_root=plugin_root)
    assert python.exists()
    expected_runtime = (
        home / ".archolith" / "venvs" / f"claude-py{os.sys.version_info.major}{os.sys.version_info.minor}"
    )
    assert python.parent.parent == expected_runtime
    assert installs == [(python, requirements)]

    marker = python.parent.parent / bootstrap.MARKER_FILE
    assert marker.read_text(encoding="utf-8").strip() == bootstrap._requirements_hash(requirements)

    second_python = bootstrap.ensure_runtime(agent="claude", plugin_root=plugin_root)
    assert second_python == python
    assert installs == [(python, requirements)]
