# Contributing to AFMX

Thank you for your interest in contributing. AFMX is Apache 2.0 licensed and welcomes contributions of all kinds.

## Quick Start
```bash
git clone https://github.com/inteleion-ai/AFMX.git
cd AFMX
python3.10 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Development Workflow
```bash
pytest tests/ -v               # full test suite
pytest tests/unit/ -v          # unit tests only (fast)
ruff check afmx/               # lint
black afmx/ tests/             # format
mypy afmx/ --ignore-missing-imports  # type check
```

## Code Standards

- Python 3.10+ — use `from __future__ import annotations`
- Async first — all I/O must be `async def`
- Pydantic v2 — use `model_config = ConfigDict(...)`
- 100 character line length (enforced by black)
- Tests required — every bug fix needs a regression test

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):
```
feat(engine): add execution resume from checkpoint
fix(retry): emit NODE_RETRYING event on each attempt
docs(quickstart): add Python SDK example
test(executor): add timeout regression test
```

## Pull Request Checklist

- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check afmx/`
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] Documentation updated if public API changed

## Questions

Open a [GitHub Discussion](https://github.com/inteleion-ai/AFMX/discussions) or email **hello@agentdyne9.com**.
