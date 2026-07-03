"""Load a local .env (if present) before any submodule reads the environment.

In local dev this picks up ANTHROPIC_API_KEY (and any TRANSLATOR_* overrides)
from a gitignored .env file at the repo root. In production there is typically
no .env — the variables come from the host environment, and load_dotenv() is a
no-op.
"""
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    # python-dotenv missing or unreadable .env — fall back to real env vars.
    pass
