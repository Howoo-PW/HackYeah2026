"""Embed the visible comments that have no vector yet, through the AI service (POST /embed), and store them.

  python scripts/embed_comments.py --dry-run   # how many comments are missing a vector
  python scripts/embed_comments.py             # embed them in batches (re-run any time: only missing ones are done)

Needs SUPABASE_DB_URL, INTERNAL_API_KEY and the AI service running (AI_SERVICE_URL, default http://localhost:8001), all from .env.
New comments are embedded by the backend itself; this is for the ones written before (and for seeds).
"""

import argparse
import os
import sys
from pathlib import Path

import httpx
import psycopg

sys.path.insert(0, str(Path(__file__).parent))
from load_seed import read_env_file  # noqa: E402

BATCH = 64


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vector) + "]"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    env = {**read_env_file(), **os.environ}
    url, key = env.get("SUPABASE_DB_URL"), env.get("INTERNAL_API_KEY")
    ai = env.get("AI_SERVICE_URL", "http://localhost:8001")
    if ai.startswith("http://ai:"):  # the Compose-internal name is not reachable from the host
        ai = "http://localhost:8001"
    if not url or not key:
        sys.exit("SUPABASE_DB_URL and INTERNAL_API_KEY must be set")
    with psycopg.connect(url, connect_timeout=15) as conn:
        conn.execute("set search_path = public, extensions")
        todo = conn.execute("""
            select c.id, c.text from public.comments c
            left join public.comment_embeddings e on e.comment_id = c.id
            where c.status = 'visible' and e.comment_id is null order by c.created_at
        """).fetchall()
        print(f"comments without a vector: {len(todo)}")
        if args.dry_run:
            return
        done = 0
        for i in range(0, len(todo), BATCH):
            batch = todo[i:i + BATCH]
            response = httpx.post(f"{ai}/embed", json={"texts": [t for _, t in batch]}, headers={"X-Internal-Key": key}, timeout=60)
            response.raise_for_status()
            body = response.json()
            with conn.cursor() as cur:
                cur.executemany(
                    "insert into public.comment_embeddings (comment_id, embedding, model) values (%s, %s::vector, %s) on conflict (comment_id) do nothing",
                    [(cid, vector_literal(v), body["model"]) for (cid, _), v in zip(batch, body["vectors"])],
                )
            conn.commit()
            done += len(batch)
            print(f"embedded {done}/{len(todo)}")


if __name__ == "__main__":
    main()
