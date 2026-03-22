"""
AFMX package entry point — python -m afmx

Python version guard runs BEFORE any afmx import so that on Python < 3.10
the user gets a clear, actionable message instead of a cryptic SyntaxError.
"""
import sys

# ── Version guard (must be FIRST — before any afmx import) ───────────────────
if sys.version_info < (3, 10):
    sys.stderr.write(
        "\n"
        "╔══════════════════════════════════════════════════════════╗\n"
        "║  AFMX requires Python 3.10 or later.                    ║\n"
        f"║  You are running Python {sys.version.split()[0]:<34}║\n"
        "║                                                          ║\n"
        "║  Fix options:                                            ║\n"
        "║    python3.10 -m afmx serve --reload                    ║\n"
        "║    python3    -m afmx serve --reload                    ║\n"
        "║    source .venv/bin/activate && python -m afmx serve    ║\n"
        "╚══════════════════════════════════════════════════════════╝\n\n"
    )
    sys.exit(1)

# ── Only import afmx after the version guard passes ───────────────────────────
from afmx.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
