#!/usr/bin/env python3
"""Load supabase/seed/*.sql into the database from SUPABASE_DB_URL (.env).

Requires: pip install "psycopg[binary]"
Order: segments_*.sql, parking.sql, finalize.sql. The inserts are idempotent
(on conflict do nothing), so the script can be re-run safely.
"""

from __future__ import annotations

import sys

import psycopg
from _common import ROOT, database_url

SEED_DIR = ROOT / "supabase" / "seed"


def main() -> None:
    db_url = database_url()

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
