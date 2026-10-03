#!/usr/bin/env python3
"""Load supabase/seed/*.sql into the database from SUPABASE_DB_URL (.env).

Requires: pip install "psycopg[binary]"
Order: segments_*.sql, parking.sql, finalize.sql. The inserts are idempotent
(on conflict do nothing), so the script can be re-run safely.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "supabase" / "seed"


def read_env_file() -> dict[str, str]:
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def main() -> None:
    db_url = os.environ.get("SUPABASE_DB_URL") or read_env_file().get("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("SUPABASE_DB_URL is not set (put it in .env)")

    files = sorted(SEED_DIR.glob("segments_*.sql")) + [SEED_DIR / "parking.sql", SEED_DIR / "finalize.sql"]
    missing = [f.name for f in files if not f.exists()]
    if missing:
        raise SystemExit(f"missing seed files: {missing}; run scripts/import_osm.py first")

    with psycopg.connect(db_url, autocommit=False) as conn:
        for f in files:
            conn.execute(f.read_text(encoding="utf-8"))
            print(f"loaded {f.name}")
        conn.commit()
        counts = conn.execute(
            "select (select count(*) from public.segments), (select count(*) from public.parking_spots)"
        ).fetchone()
        print(f"segments: {counts[0]}, parking_spots: {counts[1]}")


if __name__ == "__main__":
    try:
        main()
    except psycopg.Error as exc:
        sys.exit(f"database error: {exc}")
