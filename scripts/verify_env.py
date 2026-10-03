"""Diagnose a checkout without printing secrets; optionally start the Compose stack."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("project-overview", "backend", "database", "ai", "frontend")
TABLES = ("profiles", "segments", "ratings", "comments", "obstacles", "parking_spots",
          "segment_photos", "segment_summaries", "segment_stats")


def executable(name: str) -> str | None:
    """Find standard tools, including Windows installers omitted from PATH."""
    found = shutil.which(name)
    if found:
        return found
    candidates = {
        "node": [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "nodejs/node.exe"],
        "docker": [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Docker/Docker/resources/bin/docker.exe"],
        "claude": [Path.home() / ".local/bin/claude.exe"],
    }
    return next((str(path) for path in candidates.get(name, []) if path.is_file()), None)


def run(args: list[str], timeout: int = 10) -> tuple[bool, str]:
    """Capture tool output for parsing; callers must not print raw secret-bearing output."""
    try:
        env = os.environ.copy()
        if Path(args[0]).is_absolute():
            # Docker invokes its credential helper by name even with an absolute CLI path.
            env["PATH"] = str(Path(args[0]).parent) + os.pathsep + env.get("PATH", "")
        result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return result.returncode == 0, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return False, ""


def read_env(path: Path) -> dict[str, str]:
    """Parse dotenv using the same library as backend settings."""
    try:
        from dotenv import dotenv_values
        return {key: value or "" for key, value in dotenv_values(path).items()}
    except ImportError:
        # Enough to diagnose a fresh checkout before dependencies are installed.
        values = {}
        if path.is_file():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip().strip('"').strip("'")
        return values


def probe(url: str, health: bool = True) -> bool:
    """Require healthy JSON status or a successful frontend response."""
    try:
        with urlopen(url, timeout=10) as response:
            if health:
                return response.status == 200 and json.load(response).get("status") == "ok"
            return response.status == 200
    except (URLError, HTTPError, ValueError, TimeoutError, OSError):
        return False


def main() -> int:
    """Run all diagnostics and return a nonzero exit code for missing requirements."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", action="store_true", help="Start/build Docker Compose and wait up to 60 seconds for health")
    parser.add_argument("--skip-services", action="store_true", help="Skip HTTP probes while the stack is stopped")
    args = parser.parse_args()
    failures = 0

    def report(ok: bool, label: str, hint: str = ""):
        nonlocal failures
        failures += not ok
        print(f"{'[OK]' if ok else '[FAIL]'} {label}" + (f" — {hint}" if not ok and hint else ""))

    for name, minimum in (("git", (2, 40)), ("docker", (24, 0)), ("node", (24, 0))):
        tool = executable(name)
        ok, output = run([tool, "--version"]) if tool else (False, "")
        match = re.search(r"(\d+)\.(\d+)", output)
        report(bool(ok and match and tuple(map(int, match.groups())) >= minimum), name, f"Zainstaluj {name} >= {minimum[0]}.{minimum[1]} i dodaj do PATH")
    report(sys.version_info >= (3, 12), "Python >= 3.12")
    docker = executable("docker")
    ok, output = run([docker, "compose", "version", "--short"]) if docker else (False, "")
    compose_version = re.match(r"v?(\d+)\.", output)
    report(bool(ok and compose_version and int(compose_version.group(1)) >= 2), "Docker Compose v2+", "Uruchom Docker Desktop")
    if docker:
        report(run([docker, "info", "--format", "{{.ServerVersion}}"])[0], "Docker daemon", "Uruchom Docker Desktop")

    env = read_env(ROOT / ".env")
    example = read_env(ROOT / ".env.example")
    report((ROOT / ".env").is_file(), ".env", "Skopiuj .env.example do .env i uzupełnij lokalnie")
    missing = sorted(set(example) - set(env))
    report(not missing, "Komplet zmiennych .env", ", ".join(missing))
    config = {**env, **{key: os.environ[key] for key in example if key in os.environ}}
    required = ["SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_DB_URL",
                "INTERNAL_API_KEY", "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"]
    if config.get("MOCK_AI", "true").lower() != "true":
        required += ["AI_PROVIDER", "AI_MODEL", "AI_API_KEY"]
    if config.get("ROUTING_PROVIDER", "ors") == "ors":
        required += ["ORS_API_KEY"]
    empty = [key for key in required if not config.get(key)]
    report(not empty, "Wymagane wartości konfiguracji", "Uzupełnij: " + ", ".join(empty))

    try:
        from redis import Redis
        with Redis.from_url(config.get("REDIS_URL", "redis://localhost:16379/0"), socket_connect_timeout=2, socket_timeout=2) as client:
            report(client.ping(), "Redis — współdzielone limity")
    except Exception:
        report(False, "Redis — współdzielone limity", "Uruchom docker compose up -d redis")

    try:
        import psycopg
        db_url = config.get("SUPABASE_DB_URL")
        if not db_url:
            raise ValueError("Missing database configuration")
        with psycopg.connect(db_url, sslmode="require", connect_timeout=5,
                             options="-c statement_timeout=5000", prepare_threshold=None) as conn:
            postgis = conn.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'postgis')").fetchone()[0]
            absent = [table for table in TABLES if conn.execute("SELECT to_regclass(%s)", ("public." + table,)).fetchone()[0] is None]
        report(postgis and not absent, "Supabase: PostGIS i schemat", "Brak PostGIS lub tabel: " + ", ".join(absent))
    except Exception:
        report(False, "Połączenie z Supabase", "Sprawdź SUPABASE_DB_URL (pooler IPv4, SSL) i zainstaluj zależności backendu")

    for path in ["CLAUDE.md", *(f".claude/skills/{skill}/SKILL.md" for skill in SKILLS)]:
        report((ROOT / path).is_file(), path)
    claude = executable("claude")
    ok, output = run([claude, "mcp", "list"], 20) if claude else (False, "")
    for server in ("supabase", "context7"):
        line = next((line for line in output.splitlines() if line.lower().startswith(server + ":")), "")
        report(ok and "connected" in line.lower(), f"MCP {server}", "W Claude Code użyj /mcp, zaloguj się i sprawdź połączenie")

    if args.start:
        # No captured Compose output is printed: it can contain secret values.
        started = bool(docker and run([docker, "compose", "up", "-d", "--build"], 300)[0])
        report(started, "docker compose up", "Sprawdź lokalnie docker compose logs i konfigurację")
        if started:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if probe("http://localhost:8000/api/v1/health") and probe("http://localhost:8001/health") and probe("http://localhost:5173", False):
                    break
                time.sleep(2)
    if not args.skip_services:
        for url, health in (("http://localhost:8000/api/v1/health", True), ("http://localhost:8001/health", True), ("http://localhost:5173", False)):
            report(probe(url, health), url, "Uruchom python scripts/verify_env.py --start")
    git = executable("git")
    if git:
        ok, branch = run([git, "branch", "--show-current"])
        report(ok and bool(branch) and branch != "main", "Gałąź robocza: " + (branch or "brak"), "Przełącz na branch swojej roli")
        ok, changes = run([git, "status", "--short"])
        print(f"[INFO] Niezacommitowane pliki: {len(changes.splitlines()) if changes else 0}")
        ok, diff = run([git, "rev-list", "--left-right", "--count", "HEAD...origin/main"])
        print(f"[INFO] Commity HEAD / origin/main: {diff if ok else 'brak origin/main'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
