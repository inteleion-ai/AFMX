---
name: Bug Report
about: Something is not working as expected
title: '[Bug] '
labels: bug
assignees: ''
---

## Describe the bug
A clear description of what the bug is.

## To Reproduce
Minimal matrix definition and Python code that reproduces the issue:

```python
from afmx import AFMXEngine, ExecutionMatrix, ExecutionContext, ExecutionRecord

matrix = ExecutionMatrix(
    name="reproduce-bug",
    nodes=[...],
    edges=[...],
)
```

## Expected behaviour
What you expected to happen.

## Actual behaviour
What actually happened. Include the full traceback if there is one.

## Environment
- AFMX version: (run `python -c "import afmx; print(afmx.__version__)"`)
- Python version: (run `python --version`)
- OS:
- Store backend: memory / redis
- AFMX_STORE_BACKEND value:

## Additional context
Any other relevant information.
