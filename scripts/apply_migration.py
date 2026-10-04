"""Apply one SQL migration file to the database in a single transaction (SUPABASE_DB_URL from .env).

  python scripts/apply_migration.py supabase/migrations/20261006120000_routing_foot.sql

All or nothing: on any error the transaction is rolled back and the database is left as it was.
The file is applied exactly as committed, so the repository and the database cannot drift apart.
Needs: pip install "psycopg[binary]"
"""

import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]


def read_env() -> dict[str, str]:
    env = dict(os.environ)
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    url = read_env().get("SUPABASE_DB_URL")
    if not url:
        sys.exit("SUPABASE_DB_URL is not set (.env)")
    sql = path.read_text(encoding="utf-8")
    with psycopg.connect(url, connect_timeout=15, autocommit=False) as conn:
        conn.execute("set local statement_timeout = '300s'")
        conn.execute("set local search_path = public, extensions")
        conn.execute(sql)
        conn.commit()
    print(f"applied {path.name}")


if __name__ == "__main__":
    try:
        main()
    except psycopg.Error as exc:
        sys.exit(f"database error (nothing was changed): {exc}")
