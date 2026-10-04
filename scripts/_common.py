"""Helpers shared by the scripts: repository root, the ignored .env and the database connection string."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_env_file() -> dict[str, str]:
    """Variables from the repository's .env (empty when there is no file); comments and blank lines are skipped."""
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def setting(name: str, default: str | None = None) -> str | None:
    """A configuration value: the process environment wins over .env."""
    return os.environ.get(name) or read_env_file().get(name) or default


def database_url() -> str:
    """SUPABASE_DB_URL from the environment or .env; exits with a hint when it is missing."""
    url = setting("SUPABASE_DB_URL")
    if not url:
        sys.exit("SUPABASE_DB_URL is not set (put it in .env)")
    return url
