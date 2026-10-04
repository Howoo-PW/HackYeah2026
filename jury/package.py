"""Package the committed origin/main sources, jury launcher and local .env using only Python's standard library."""

import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    "backend", "ai-service", "frontend", "docs", "supabase", "scripts", "submission",
    "README.md", "brief.md", "brief-short.md", "IMPLEMENTATION_PLAN.md",
    ".env.example", ".gitignore", "docker-compose.yml",
)
EXTRAS = (
    "JURY.md", "docker-compose.jury.yml", "jury/frontend.Dockerfile",
    "jury/frontend.Dockerfile.dockerignore", "jury/nginx.conf",
    "jury/SCENARIUSZ_OCENY.md", "jury/package.py",
)


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "submission/jury/RateMyRoad-jury.zip")
    args = parser.parse_args()
    missing = [name for name in (*EXTRAS, ".env") if not (ROOT / name).is_file()]
    if missing:
        print("Brak plikow: " + ", ".join(missing), file=sys.stderr)
        return 1
    output = args.output.resolve()
    # Output belongs to a dedicated artifact directory, never alongside app sources.
    artifact_dir = (ROOT / "submission/jury").resolve()
    if not output.is_relative_to(artifact_dir) or output.suffix.lower() != ".zip":
        print("ZIP musi znajdowac sie w submission/jury/.", file=sys.stderr)
        return 1
    revision = git("rev-parse", "origin/main").decode().strip()
    source = git("archive", "--format=zip", revision, "--", *SOURCE_PATHS)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(BytesIO(source)) as committed, ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for entry in committed.infolist():
            if entry.is_dir():
                continue
            # The local environment is supplied separately, never taken from source control.
            if Path(entry.filename).name.startswith(".env") and entry.filename != ".env.example":
                continue
            archive.writestr("RateMyRoad/" + entry.filename, committed.read(entry.filename))
        for name in (*EXTRAS, ".env"):
            archive.write(ROOT / name, "RateMyRoad/" + name)
        manifest = {
            "project": "Rate My Road",
            "repository": "https://github.com/Howoo-PW/HackYeah2026",
            "source_ref": "origin/main",
            "source_commit": revision,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        archive.writestr("RateMyRoad/jury/BUILD.json", json.dumps(manifest, indent=2) + "\n")
        archive.writestr("RateMyRoad/START.txt", "Rate My Road - start\n\nPrzeczytaj JURY.md. Plik .env jest juz uzupelniony.\nPrzy uruchomionym Docker Desktop wykonaj w tym folderze:\n\ndocker compose --env-file .env -f docker-compose.jury.yml up --build --wait --wait-timeout 180\n\nOtworz http://localhost:5173\nScenariusz oceny: jury/SCENARIUSZ_OCENY.md\n")
    print(f"Gotowa paczka: {output}")
    print(f"Zrodla aplikacji: origin/main @ {revision[:7]}")
    print("Paczka zawiera .env z sekretami; przekaz ja prywatnie jury.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
