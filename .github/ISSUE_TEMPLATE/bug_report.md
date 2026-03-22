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
Minimal matrix definition and code that reproduces the issue:
```python
from afmx import AFMXEngine, ExecutionMatrix
matrix = ExecutionMatrix(name="reproduce", nodes=[...], edges=[...])
```

## Expected behaviour

## Actual behaviour
Include the full traceback if there is one.

## Environment
- AFMX version: (run `python -c "import afmx; print(afmx.__version__)"`)
- Python version:
- OS:
- Store backend: memory / redis
