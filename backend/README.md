# Backend B1

Endpointy i modele: [kontrakt](../docs/CONTRACT.md). Dokumentacja działającego API: http://localhost:8000/docs.

## Lokalnie

Z katalogu repo:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
.venv/Scripts/python.exe -m pytest -c backend/pytest.ini backend/tests -q
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --port 8000 --reload
```

Backend czyta `.env` z root niezależnie od katalogu uruchomienia; opcjonalne
backend/.env ma pierwszeństwo, potem zmienne środowiska.
SUPABASE_DB_URL: adres Supabase poolera IPv4 z hasłem, SSL wymagany. Backend
korzysta z psycopg zamiast Data API dla zapytań przestrzennych i transakcji.
Połączenie DB jest uprzywilejowane; wszystkie zapisy kontroluje backend.
SERVICE_ROLE_KEY jest przeznaczony dla modułu Storage B2/skryptu admina;
nie przekazuj go do frontendu. Nie ma lokalnej bazy ani produkcyjnych mocków core.

## Zachowanie

- JWT ES256/RS256: JWKS, issuer, audience, exp, iat, sub i role authenticated.
- JWT HS256: weryfikacja online przez Supabase Auth; bez współdzielonego sekretu JWT.
- Admin tylko z app_metadata, nigdy user_metadata. Zmiana roli w JWT staje się
  widoczna po odświeżeniu tokenu; frontend korzysta z Supabase Auth.
- Oceny: 1 na użytkownika/odcinek/dzień Warszawy, atomowe zastąpienie 200/201.
- Limity prób zapisu: 30 ocen/h i 10 komentarzy/h; routing 30/min na IP.
  Atomowy limiter Redis współdzieli kwotę między procesami. Compose zachowuje
  dane w wolumenie AOF. Lokalny REDIS_URL: redis://localhost:16379/0.
- Statystyki ocen liczone na żywo; segment_stats i jego odświeżanie pozostają u B2.
- Moderacja komentarza usuwa cache AI odcinka. Publiczny odczyt tylko visible.
- Health zwraca 503/down przy braku DB, 200/degraded przy niedostępnym AI/trasach.
  Routing w health sprawdza konfigurację, bez zużywania limitu dostawcy.

## Integracja zespołu

Routing i serwis AI scalono z core. Kolejne routery B2 montuj obok core_router.
Zachowaj lifespan i obsługę błędów. Klucze SecretStr czytaj przez get_secret_value().
Kontraktu nie zmieniono. Mock routingu wybieraj jawnie przez ROUTING_PROVIDER=mock.

## Weryfikacja

Testy offline sprawdzają kontrakt, walidację, role, podpis JWT, limity i DST;
repozytorium DB w testach API jest zastępowane fixture, więc nie dowodzą zapisów
w rzeczywistej bazie. Zapytania SQL dodatkowo sprawdzane read-only w Supabase.
Pełny test Auth/zapisów wymaga lokalnie uzupełnionego .env i danych seed B2.

Aktualne źródła: [Supabase JWT](https://supabase.com/docs/guides/auth/jwts),
[Psycopg](https://www.psycopg.org/psycopg3/docs/),
[FastAPI testy](https://fastapi.tiangolo.com/tutorial/testing/),
[PyJWT](https://pyjwt.readthedocs.io/en/stable/api.html).
