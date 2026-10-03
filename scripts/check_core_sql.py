"""Generate read-only EXPLAIN statements from the actual B1 repository queries."""

import json
from pathlib import Path
import sys
from datetime import datetime, timezone
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from psycopg.sql import Literal
from app.auth import User
from app.repository import Repository
from app.schemas import RatingCreate


class Collector:
    """Collect actual queries, supplying structural fixtures for dependent reads."""

    def __init__(self):
        self.queries = []
        self.current = ""

    def execute(self, query, params=()):
        self.current = query
        parts = query.split("%s")
        if len(parts) != len(params) + 1:
            raise ValueError("Parameter count mismatch")
        bound = parts[0] + "".join(Literal(value).as_string() + part for value, part in zip(params, parts[1:]))
        self.queries.append("EXPLAIN (FORMAT JSON) " + bound + ";")
        return self

    def fetchone(self):
        if "SELECT summary," in self.current:
            return None
        if "INSERT INTO public.comments" in self.current:
            return {"id": UUID("22222222-2222-4222-8222-222222222222")}
        return {"id": 1, "count": 0}

    def fetchall(self):
        return []


def main():
    """Print EXPLAIN-only SQL; no statement executes writes, even on a live DB."""
    conn = Collector()
    repo = Repository(conn)
    user = User(UUID("11111111-1111-4111-8111-111111111111"), "test@example.invalid")
    repo.profile(user)
    repo.segments((19.792, 49.967, 20.217, 50.126), "surface", 3, True)
    repo.nearest(50.06, 19.94)
    repo.segment(1, user.id)
    repo.rate(1, user.id, RatingCreate(surface=4), datetime(2026, 10, 3, tzinfo=timezone.utc))
    repo.comments(1, 1, 20)
    repo.comment(1, user.id, "Test parametrization: ' quote")
    repo.moderate_comment(UUID("22222222-2222-4222-8222-222222222222"), "hidden")
    print(json.dumps({"count": len(conn.queries), "sql": "SET search_path = public, extensions;\n" + "\n".join(conn.queries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
