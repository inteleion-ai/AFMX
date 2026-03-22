# AFMX — Installation & Quick Start Guide

## Python Version

AFMX requires **Python 3.10 or higher**.

Your system may have multiple Python versions. Always use `python3.10` (or `python3`)
explicitly — never `python` alone (that may resolve to the system Python 3.6).

---

## Step 1 — Verify Python version

```bash
python3.10 --version   # Must be 3.10.x or higher
# or
python3 --version
```

---

## Step 2 — Install AFMX

```bash
cd /home/opc/afmx

# Option A: editable install (recommended for development)
python3.10 -m pip install -e ".[dev]"

# Option B: plain install from requirements.txt
python3.10 -m pip install -r requirements.txt
```

---

## Step 3 — Add ~/.local/bin to PATH (once)

After a `--user` install, pip places scripts in `~/.local/bin`.
Add it to your PATH so the `afmx` CLI works:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

---

## Step 4 — Start the server

```bash
# Using the module entry point (always works):
python3.10 -m afmx serve --reload

# Or using the installed CLI (after PATH fix above):
afmx serve --reload
```

Server starts at: http://localhost:8100
API docs at:      http://localhost:8100/docs

---

## Step 5 — Run tests

```bash
python3.10 -m pytest tests/ -v
```

---

## Step 6 — Use the CLI

```bash
# Health check
python3.10 -m afmx health

# Validate a matrix file
python3.10 -m afmx validate --matrix examples/matrix.json

# Execute a matrix
python3.10 -m afmx run \
  --matrix examples/matrix.json \
  --input '{"task":"hello"}' \
  --verbose

# List recent executions
python3.10 -m afmx list

# Get status of an execution
python3.10 -m afmx status <execution_id>
```

---

## Docker (no Python version concerns)

```bash
# Build and run
docker build -t afmx:latest .
docker run -p 8100:8100 afmx:latest

# Full stack with Redis + Prometheus
docker-compose up -d
```

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `SyntaxError: future feature annotations is not defined` | Running with Python 3.6 | Use `python3.10` instead of `python` |
| `afmx: command not found` | `~/.local/bin` not in PATH | Run `export PATH="$HOME/.local/bin:$PATH"` |
| `Cannot import 'setuptools.backends.legacy'` | Old pyproject.toml build backend | Fixed in this version |
| `ValidationError: timeout_seconds ge=1` | Old node.py TimeoutPolicy | Fixed in this version |
| `pip install` fails | Wrong Python version being used | Use `python3.10 -m pip install` |
