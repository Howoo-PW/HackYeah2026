# B1 ? wykonanie i dalsza konfiguracja

Branch u?ytkownika: `backend/b1-howoo`. Pierwszy commit B1: `4bfdf0a`.
Zintegrowano `origin/ai/service`, `origin/backend/routing`, `origin/frontend/map`
oraz migracje B2 obecne w `origin/main`. G??wny branch pozostaje bez zmian B1.

## Zrealizowane kroki

| Punkt | Wynik |
|---|---|
| 1. Konfiguracja | Klucze publiczne Supabase pobrane przez plugin do ignorowanego .env; INTERNAL_API_KEY wygenerowany. Has?o DB i service_role odroczone na pro?b? u?ytkownika. |
| 2. Uruchomienie | Redis, mapa, backend i AI uruchomione w kontenerach; frontend korzysta z fallbacku demo, AI i routing z mock?w. Seed online pozostaje do wykonania po wskazaniu konta Supabase. |
| 3. Testy | 70 test?w backendu, 10 AI, frontend build i lint PASS. Routing HTTP zwraca 3 trasy, AI podsumowuje 5 komentarzy. Realny JWT i zapisy DB odroczone bez sekret?w. |
| 4. MCP | Context7 initialize/tools/list PASS; Supabase plugin dzia?a. Bezpo?redni endpoint Supabase MCP odpowiada 401 i wymaga osobistego OAuth. |
| 5. Integracja branchy | FE, AI, routing i migracje B2 po??czone na branchu B1; zachowano core, JWT, transakcje i error handlers. |
| 6. Wiele proces?w | Wsp??dzielony limiter Redis z atomowym Lua, TTL i trwa?ym wolumenem; sprawdzono r?wnoczesne pr?by dw?ch klient?w. Routing 30/min na IP. |
| 7. Ochrona main | Dodano GitHub Actions: backend, AI, frontend. Konfiguracja administracyjna ochrony main sprawdzana osobno. |

## Dost?p lokalny

- Mapa: http://localhost:5173
- Dokumentacja API: http://localhost:8000/docs
- AI health: http://localhost:8001/health
- Redis tego projektu: localhost:16379 (port 6379 zaj?ty przez inn? us?ug?).

Backend dzia?a, ale jego health poprawnie zwraca HTTP 503/down bez
SUPABASE_DB_URL. Frontend pokazuje dane demonstracyjne, nie dane online.
Przy normalnym starcie Compose frontend czeka na zdrow? baz?; tryb demo
uruchomiono osobnym `docker compose up -d --no-deps frontend`.

## Brakuj?ce dane

U?ytkownik wybra? kontynuowanie bez kluczy. Do pe?nej integracji potrzebne s?:

- SUPABASE_DB_URL: adres poolera PostgreSQL z has?em, SSL wymagany.
- SUPABASE_SERVICE_ROLE_KEY: tylko backend/Storage i skrypt administratora.
- Konto dev do test?w: DEV_ADMIN_EMAIL i DEV_ADMIN_PASSWORD w lokalnym .env.
- Dla prawdziwych tras: ROUTING_PROVIDER=ors i ORS_API_KEY; obecnie mock.

Plugin Supabase udost?pnia klucze publiczne, nie has?o DB ani service_role.
Oba podpi?te konta (Supabase i Primary) widz? ten sam projekt; przed zapisami
narz?dzia wymagaj? wskazania konta. Nie zmieniano zdalnych danych ani Auth.

Po uzupe?nieniu sekret?w: `python scripts/verify_env.py --start`, seed B2,
pr?ba loginu, ocena 201/200, komentarz, moderacja i od?wie?enie mapy.
Kontrakt API pozosta? bez zmian. Sekrety i rola lokalna s? ignorowane przez git.
