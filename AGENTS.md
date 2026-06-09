# AGENTS.md

## Project Instructions For Coding Agents

1. Before making changes, read the guidance files in `.agent/`.
2. Start with `.agent/README.md` for project workflow and conventions.
3. Use `.agent/data_models.md` for entity and schema expectations.
4. Use `.agent/architecture.md` for system design and external API context.
5. Check `.agent/workflows/` for task-specific runbooks before executing operational actions.
6. If there is a conflict between code and `.agent` docs, call it out explicitly and ask for clarification.

## Scope

These instructions apply to the entire repository.

## Build / Lint / Test Commands

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run single test file
pytest tests/test_attributor.py

# Lint
ruff check .

# Auto-fix lint issues
ruff check --fix .
```

## Code Style

See `.agent/workflows/code_conventions.md` for full rules. Key points:

- Python 3.11+, 4 spaces indent, 120 char max line length
- Builtin generics (`list`, `dict`), `X | Y` unions, not `typing.List`/`Optional`
- `%s`-style lazy formatting for loggers
- snake_case for modules/functions, PascalCase for classes

## Project-Specific Notes

- This is a **diagnostic tool** — it measures and reports, it does NOT modify MCP traffic
- Token counting uses tiktoken as a proxy for Anthropic's tokenizer (known limitation, documented)
- The live accumulator reads archolith-filter's FilterTelemetryStore; it does NOT add pipeline stages
- Waste detectors use heuristics and will have false positives/negatives — start conservative, tune later
- Server mapping and schema catalog are configurable JSON files in `data/`
