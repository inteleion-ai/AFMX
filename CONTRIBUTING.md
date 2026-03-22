# Contributing to AFMX

Thank you for contributing. AFMX is Apache 2.0 licensed.

## Setup
```bash
git clone https://github.com/inteleion-ai/AFMX.git
cd AFMX
python3.10 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Workflow
```bash
pytest tests/ -v        # run tests
ruff check afmx/        # lint
black afmx/ tests/      # format
```

## Commit style
Use [Conventional Commits](https://www.conventionalcommits.org/):
`feat(engine):`, `fix(retry):`, `docs(quickstart):`, `test(executor):`

## PR checklist
- [ ] `pytest tests/` passes
- [ ] `ruff check afmx/` passes
- [ ] CHANGELOG.md updated under `[Unreleased]`

Questions: open a [Discussion](https://github.com/inteleion-ai/AFMX/discussions) or email **hello@agentdyne9.com**.
