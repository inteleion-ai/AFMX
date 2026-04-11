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
pytest tests/ -v        # run all tests
ruff check afmx/        # lint
black afmx/ tests/      # format
mypy afmx/              # type-check
```

## Commit style

Use [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Use for |
|--------|---------|
| `feat(adapter):` | new features |
| `fix(engine):` | bug fixes |
| `docs(quickstart):` | documentation |
| `test(executor):` | tests only |
| `chore(ci):` | CI / tooling |
| `refactor(router):` | refactors |

## PR checklist

- [ ] `pytest tests/` passes
- [ ] `ruff check afmx/` passes (no errors)
- [ ] `black --check afmx/ tests/` passes
- [ ] `mypy afmx/` passes (or improvement only)
- [ ] CHANGELOG.md updated under `[Unreleased]` section
- [ ] New public API exports added to `afmx/__init__.py` and `__all__`
- [ ] Apache 2.0 license header present in new `.py` files
- [ ] Docstrings on all public classes and functions

## License headers

Every new `.py` file must start with:

```python
# Copyright 2026 Agentdyne9
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
```

## Questions

Open a [Discussion](https://github.com/inteleion-ai/AFMX/discussions) or
email **hello@agentdyne9.com**.

## TypeScript SDK

The TypeScript SDK lives in `sdk/typescript/`. To contribute:

```bash
cd sdk/typescript
npm install
npm run typecheck   # tsc --noEmit
npm run build       # compile to dist/
```

All public API surface must have JSDoc comments. The SDK must have zero runtime
dependencies (`dependencies` in `package.json` must remain empty). Follow the
same Conventional Commits style as the Python codebase.
