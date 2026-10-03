"""Create a demo administrator only in dev, with credentials from the ignored .env."""

from pathlib import Path
import sys

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Create an email-confirmed admin without logging email, password or keys."""
    import os
    config = {**dotenv_values(ROOT / ".env"), **os.environ}
    if config.get("APP_ENV") != "dev":
        print("[FAIL] Tworzenie administratora jest dozwolone tylko dla APP_ENV=dev")
        return 1
    required = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "DEV_ADMIN_EMAIL", "DEV_ADMIN_PASSWORD")
    missing = [key for key in required if not config.get(key)]
    if missing:
        print("[FAIL] Uzupełnij lokalnie: " + ", ".join(missing))
        return 1
    try:
        key = config["SUPABASE_SERVICE_ROLE_KEY"]
        headers = {"apikey": key}
        # New secret keys are API keys, not JWTs. Legacy service_role keys are both.
        if not key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {key}"
        with httpx.Client(timeout=10) as client:
            response = client.post(config["SUPABASE_URL"].rstrip("/") + "/auth/v1/admin/users",
                headers=headers, json={"email": config["DEV_ADMIN_EMAIL"], "password": config["DEV_ADMIN_PASSWORD"],
                "email_confirm": True, "app_metadata": {"role": "admin"}, "user_metadata": {"display_name": "Demo admin"}})
        if response.status_code not in (200, 201):
            print(f"[FAIL] Supabase Auth: HTTP {response.status_code}; sprawdź lokalnie konfigurację lub istniejące konto")
            return 1
        print("[OK] Utworzono administratora dev. Zaloguj się przez Supabase Auth.")
        return 0
    except httpx.HTTPError:
        print("[FAIL] Supabase Auth jest niedostępny")
        return 1


if __name__ == "__main__":
    sys.exit(main())
