# archolith-audit pre-publish checklist

Run this before publishing any `archolith-audit` Python package or standalone plugin bundle.

## Core package

- [ ] Worktree is clean except for intentional release-version changes.
- [ ] `python -m ruff check archolith_mcp_audit tests scripts`
- [ ] `$env:TMP='C:\tmp'; $env:TEMP='C:\tmp'; python -m pytest tests -q`
- [ ] `python -m pip install -e . --dry-run --no-deps`
- [ ] `pyproject.toml` declares `license = "Apache-2.0"`.
- [ ] Root `LICENSE` is Apache-2.0.
- [ ] `THIRD-PARTY-LICENSES.md` reflects the exact dependency set being published.

## Plugin bundles

- [ ] `python scripts\release.py sync`
- [ ] `python scripts\release.py check`
- [ ] `python scripts\release.py build`
- [ ] `dist/archolith-audit-plugin-claude/LICENSE` exists.
- [ ] `dist/archolith-audit-plugin-codex/LICENSE` exists.
- [ ] `dist/archolith-audit-plugin-gemini/LICENSE` exists.
- [ ] `dist/archolith-audit-plugin-opencode/LICENSE` exists.
- [ ] `dist/*/THIRD-PARTY-LICENSES.md` exists.
- [ ] Plugin manifests/package files declare `Apache-2.0`.
- [ ] Plugin manifests/package files point at their standalone `Archolith/archolith-audit-plugin-*` repos.
- [ ] Plugin README install instructions point at the standalone repos/packages.

## Runtime gates

- [ ] Claude plugin passes `.agent/workflows/plugin_runtime_verification.md`.
- [ ] Codex plugin passes `.agent/workflows/plugin_runtime_verification.md`.
- [ ] Gemini plugin passes `.agent/workflows/plugin_runtime_verification.md`.
- [ ] OpenCode plugin passes `.agent/workflows/plugin_runtime_verification.md`.

## Publish

- [ ] Standalone plugin repos exist under `https://github.com/Archolith/`.
- [ ] Copy each `dist/archolith-audit-plugin-*` directory to the matching standalone repo.
- [ ] Commit, tag, and push each standalone repo.
- [ ] Publish npm-capable plugins from the matching `dist/` directories only after runtime verification.
- [ ] Record published versions and verification evidence in `.agent/CHANGELOG.md`.
