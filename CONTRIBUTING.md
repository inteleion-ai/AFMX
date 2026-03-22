# Contributing to AFMX

Thank you for your interest in contributing. AFMX is Apache 2.0 licensed and welcomes contributions of all kinds — bug fixes, new adapters, documentation improvements, and feature work aligned with the roadmap.

---

## Quick Start

```bash
git clone https://github.com/inteleion-ai/AFMX.git
cd AFMX
python3.10 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Before You Start

- Check [open issues](https://github.com/inteleion-ai/AFMX/issues) to avoid duplicate work
- For significant changes, open an issue first to discuss the approach
- For bug fixes, a PR with a failing test + fix is the fastest path to merge

---

## Development Workflow

```bash
# Run the full test suite
pytest tests/ -v

# Run only unit tests (fast, no server needed)
pytest tests/unit/ -v

# Run linter
ruff check afmx/

# Run formatter
black afmx/ tests/

# Type check
mypy afmx/ --ignore-missing-imports

# Test against a live server
python3.10 -m afmx serve --reload &
python scripts/test_realtime.py
```

---

## Code Standards

- **Python 3.10+** — use `from __future__ import annotations` for forward refs
- **Async first** — all I/O operations must be `async def`
- **Pydantic v2** — use `model_config = ConfigDict(...)`, not `class Config`
- **No bare `except:`** — always catch specific exception types
- **Docstrings** — public classes and functions need a one-line summary
- **Tests required** — every bug fix needs a regression test; every new feature needs unit tests
- **Line length** — 100 characters (enforced by black)

---

## Adding a New Adapter

1. Create `afmx/adapters/myframework.py`
2. Inherit from `AFMXAdapter` in `afmx/adapters/base.py`
3. Implement `name`, `to_afmx_node()`, `execute()`, `normalize()`
4. Register in `afmx/adapters/registry.py`
5. Add unit tests in `tests/unit/test_adapters.py`
6. Add documentation in `docs/adapters.md`

---

## Adding a New Handler

Add to `afmx/startup_handlers.py`:

```python
async def my_handler(node_input: dict, context, node) -> dict:
    return {"result": node_input["input"]}

# In register_all():
("my_handler", my_handler, "tool", "Description", ["tag1"]),
```

---

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(engine): add execution resume from checkpoint
fix(retry): emit NODE_RETRYING event on each attempt
docs(quickstart): add TypeScript example
test(executor): add timeout regression test
chore(deps): bump fastapi to 0.111.1
```

Types: `feat` `fix` `docs` `test` `chore` `refactor` `perf` `ci`

---

## Pull Request Checklist

- [ ] Tests added or updated
- [ ] `pytest tests/` passes
- [ ] `ruff check afmx/` passes (zero warnings)
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] Documentation updated if public API changed

---

## Questions

Open a [GitHub Discussion](https://github.com/inteleion-ai/AFMX/discussions) or email **hello@agentdyne9.com**.
