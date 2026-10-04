---
name: backend
description: Backend FastAPI, core API, JWT, transakcje i testy. Właściciel B1.
---

# Backend

Najpierw project-overview i docs/CONTRACT.md. API /api/v1; OpenAPI /docs.

## Struktura i konwencje

- app/main.py: montowanie routerów, CORS, lifecycle puli, health.
- app/config.py: konfiguracja; SecretStr dla kluczy i DB URL; .env z katalogu repo.
- app/auth.py: ES256/RS256 przez JWKS z issuer/audience/expiry; HS256 przez
  Supabase /auth/v1/user. Nigdy nie autoryzuj z user_metadata.
- app/database.py: pula 0–5 połączeń, SSL, timeout, prepare_threshold=None
  dla Supavisor; synchroniczne route'y działają w wątkach, również na Windows.
- app/repository.py: parametryzowane SQL; schemat B2; żadnego DDL.
- app/core.py: endpointy B1; app/schemas.py: Pydantic zgodny z kontraktem.
- app/errors.py: wspólny format błędów; bez wartości wejścia i sekretów.
- app/rate_limit.py: współdzielony Redis i atomowy Lua; Memory wyłącznie w testach.
  Compose używa redis:6379, lokalne skrypty localhost:16379.

- app/routing/: `router.py` POST /route (limit 30/min na IP); `graph.py` auto i rower z własnego
  grafu w bazie (`find_route`, `routing_snap`, wagi użytkownika; opis w docs/ROUTING_GRAPH.md);
  `scoring.py` ogólny wynik trasy wg wag. Auto, rower i piesi z jednego grafu (ORS i mock usunięte).

Wstawiaj routery B2/AI obok core_router; nie kopiuj ich implementacji.
Ocena: unique(user_id,segment_id,rated_on); advisory lock i UPSERT w jednej
transakcji. rated_on i domyślna pora dnia według Europe/Warsaw, daty API UTC.
Nowa ocena 201, zastąpienie 200. Licz statystyki na żywo, by mapa widziała zapis.
Komentarze publiczne tylko visible; moderacja admin usuwa cache podsumowania.
Dependency get_repository ma scope=function: commit przed wysłaniem odpowiedzi.

## Weryfikacja i dokumentowanie

Z root: .venv/Scripts/python.exe -m pytest -c backend/pytest.ini backend/tests.
Z backend: python -m pytest -q. Zależności w requirements-dev.txt.
Po zmianie: docstringi publicznych funkcji, aktualizacja tego skilla i overview
(struktura, Stan, TODO) oraz docs/journal/B1.md. Kontrakt w osobnym PR.
Dokumentacja: Context7, oficjalne Supabase/FastAPI/Psycopg/PyJWT.

## Stan

- backend/b1-howoo: core API, JWT i moderacja, bounded pool i transakcje.
- Walidacja Krakowa, limit 2000 odcinków, paginacja max 100, oceny całkowite 1–5.
- Testy core/Redis; test równoczesnych klientów sprawdza wspólną kwotę.
- Integrację routingu wycofano; health raportuje routing=not_configured.
- scripts/verify_env.py i scripts/create_dev_admin.py (tylko APP_ENV=dev).
- 22 plany zapytań SQL sprawdzone na online Supabase; obraz Docker Python 3.12
  zbudowany i test API w kontenerze PASS. Pełna integracja wymaga kluczy w .env.

- 2026-10-05, backend/graph-routing: POST /route dla auta i roweru z własnego grafu (rank 1 wg wag
  użytkownika, rank 2 najszybsza), limit 30/min na IP, snap max 600 m, health routing sprawdza graf.
  Testy: offline test_graph_routing.py i opcjonalny test_graph_db.py (RUN_DB_TESTS=1).

- 2026-10-04, backend/foot-routing: `foot-walking` z grafu (po drogach), ORS, mock, przykładowe segmenty i `shapely`
  usunięte; `/health` sprawdza graf trzech profili; granice obszaru tylko w `app/geo.py`.

## TODO

- backend/b1-howoo: test pełnej integracji na .env zespołu i rzeczywistym JWT.
- Piesi: faza 2 tylko gdyby brakowało ścieżek w parkach lub chodników (samodzielne `footway`, schody, przejścia).
- Przeszkody, pora dnia i parkingi przy celu w koszcie grafu (B2); `score` bywa null: osobny PR do kontraktu.
- Współdzielony limiter gotowy; produkcja wymaga chronionego dostępu do Redis.
- B2: schemat/seed i odświeżanie segment_stats; B2/AI routery dodają właściciele.
