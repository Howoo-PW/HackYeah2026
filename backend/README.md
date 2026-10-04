# Backend B1

Endpointy i modele: [kontrakt](../docs/CONTRACT.md). Dokumentacja działającego API: http://localhost:8000/docs.

## Lokalnie

Z katalogu repo:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
.venv/Scripts/python.exe -m pytest -c backend/pytest.ini backend/tests -q
docker compose up -d redis ai
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
- Limity prób zapisu: 30 ocen/h i 10 komentarzy/h.
  Atomowy limiter Redis współdzieli kwotę między procesami. Compose zachowuje
  dane w wolumenie AOF. Lokalny REDIS_URL: redis://localhost:16379/0.
- Statystyki ocen liczone na żywo; segment_stats i jego odświeżanie pozostają u B2.
- Moderacja komentarza usuwa cache AI odcinka. Publiczny odczyt tylko visible.
- Health zwraca 503/down przy braku DB, 200/degraded przy niedostępnym AI/trasach.
  `routing`: ok przy zbudowanym grafie auta, roweru i pieszych, not_configured bez bazy, error bez grafu.

## Trasy (`POST /api/v1/route`)

- Auto, rower i piesi: własny graf w Supabase (`routing/graph.py`, SQL `find_route`), z wagami użytkownika dla
  nawierzchni, widoków, bezpieczeństwa, ruchu i parkingów. Rank 1 to trasa wg wag, rank 2 najszybsza.
  Szczegóły i definicje pól: [docs/ROUTING_GRAPH.md](../docs/ROUTING_GRAPH.md). Piesi chodzą po drogach (nie po chodnikach).
  Zewnętrznego silnika tras (ORS) i mocka już nie ma.
- Opcjonalne `via` (do 5 punktów pośrednich, w kolejności) działa dla wszystkich profili.
- Opcjonalne `time_of_day` (`morning|day|evening|night`, domyślnie aktualna pora w Warszawie): trasa i pokazane oceny
  liczą oceny z tej pory (zmieszane z ocenami ogólnymi).
- Przeszkody (`app/obstacles.py`): `GET /obstacles?bbox=`, `POST /obstacles` (10/h), `DELETE /admin/obstacles/{id}`.
  Aktywne przeszkody zmieniają trasy auta, roweru i pieszych na żywo (zamknięcie blokuje krawędź, reszta wydłuża czas).
- Limit 30 żądań/min na IP; punkt poza obsługiwanym obszarem 422; punkt dalej niż 600 m od drogi 404.
- Testy: `tests/test_graph_routing.py` (offline) i `tests/test_graph_db.py` (opcjonalnie, `RUN_DB_TESTS=1`,
  prawdziwa baza, tylko odczyty).

## Integracja zespołu

Routery B2/AI montuj obok core_router w osobnym kroku integracji.
Zachowaj lifespan i obsługę błędów. Klucze SecretStr czytaj przez get_secret_value().
Klucz dostawcy AI nie jest wymagany (`MOCK_AI=true`).

## Weryfikacja

Testy offline sprawdzają kontrakt, walidację, role, podpis JWT, limity i DST;
repozytorium DB w testach API jest zastępowane fixture, więc nie dowodzą zapisów
w rzeczywistej bazie. Zapytania SQL dodatkowo sprawdzane read-only w Supabase.
Pełny test Auth/zapisów wymaga lokalnie uzupełnionego .env i danych seed B2.

Aktualne źródła: [Supabase JWT](https://supabase.com/docs/guides/auth/jwts),
[Psycopg](https://www.psycopg.org/psycopg3/docs/),
[FastAPI testy](https://fastapi.tiangolo.com/tutorial/testing/),
[PyJWT](https://pyjwt.readthedocs.io/en/stable/api.html).
