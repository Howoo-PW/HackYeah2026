# B1 — uruchomienie i zakres pracy

Branch: `backend/b1-howoo`. Draft: https://github.com/Howoo-PW/HackYeah2026/pull/2.
Integracje frontend/map, ai/service i backend/routing wycofano nowym commitem
bez przepisywania historii. Zostały core B1, JWT, odcinki, oceny, komentarze,
moderacja, limiter Redis, testy, diagnostyka i CI. Migracje B2 są już w main.
Frontend i AI wróciły do wspólnych szkieletów z main; mapa nie jest dostępna.
Nie zmieniono danych Supabase ani ustawień zdalnych.

## Konfiguracja

Nie nadpisuj istniejącego .env. Sekrety wpisuj tylko lokalnie.
Core B1 wymaga SUPABASE_URL, SUPABASE_ANON_KEY i SUPABASE_DB_URL.
Adres projektu i klucz publiczny zostały wcześniej uzupełnione.

SUPABASE_DB_URL: Supabase Dashboard → projekt → Connect → Transaction pooler.
Skopiuj pełny connection string i zastąp placeholder hasłem bazy PostgreSQL.
Znaki specjalne hasła zakoduj jako URL. Według dziennika B2 działa port 6543,
a 5432 nie odpowiada z Dockera. Backend wymusza SSL i wyłącza prepared statements.

REDIS_URL=redis://localhost:16379/0 dla pracy poza Dockerem.
Compose automatycznie ustawia redis://redis:6379/0.

SUPABASE_SERVICE_ROLE_KEY nie jest wymagany przez core B1 dla odczytów,
ocen ani komentarzy. Potrzebują go skrypt admina dev i przyszły Storage B2.
Legacy service_role znajdziesz w ustawieniach API Keys projektu.
DEV_ADMIN_EMAIL i DEV_ADMIN_PASSWORD są potrzebne tylko do skryptu admina.
Klucze AI i ORS nie są potrzebne dla tego brancha.
Nie wklejaj sekretów do czatu ani do zmiennych VITE_*.

Źródła:
- https://supabase.com/docs/guides/database/connecting-to-postgres
- https://supabase.com/docs/guides/getting-started/api-keys

## Uruchomienie w PowerShell

Uruchom Docker Desktop, potem w katalogu repo:

```powershell
docker compose up -d --build redis ai backend
```

- API i Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health
- Szkielet AI: http://localhost:8001/health

Bez poprawnego DB URL Swagger działa, health zwraca 503/down,
a operacje bazodanowe nie działają. Z bazą health może zwracać 200/degraded,
ponieważ routing pozostaje niezintegrowany na B1.

Opcjonalny ekran szkieletu frontendu (bez mapy):

```powershell
docker compose up -d --build --no-deps frontend
```

Otwórz http://localhost:5173.

## Weryfikacja

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
$env:REDIS_TEST_URL = 'redis://localhost:16379/0'
.venv/Scripts/python.exe -m pytest -c backend/pytest.ini backend/tests -q
.venv/Scripts/python.exe scripts/verify_env.py --skip-services
```

Diagnostyka sprawdza również narzędzia i MCP; ich brak nie oznacza błędu API.
Testy API korzystają z zastępczego repozytorium i nie potwierdzają zapisów w DB.
Po konfiguracji DB sprawdź publiczne GET /api/v1/segments w Swaggerze.
Oceny i komentarze wymagają access tokenu użytkownika Supabase w nagłówku
Authorization: Bearer <access_token>. Klucz anon nie zastępuje JWT.
Seed i migracje utrzymuje B2; nie uruchamiaj ich ponownie w ramach B1.

## Pozostało

Uzupełnić połączenie DB i sprawdzić rzeczywiste odczyty, login, ocenę
(201, następnie 200), komentarz i moderację. Integracja FE/AI jest osobnym
zadaniem zespołu. Ochrona main ustawiona wcześniej pozostaje aktywna.
