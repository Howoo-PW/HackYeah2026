# B1 — analiza i przekazanie pracy

2026-10-03. Branch użytkownika: `backend/b1-howoo`, oparty na `origin/main`
z migracjami B2 (`93d01d9`). Zmiany B1 pozostają w katalogu roboczym.

## Analiza branchy

| Branch zdalny | Stan | Znaczenie dla B1 |
|---|---|---|
| main | Szkielety usług, kontrakt, scalony db/schema | Baza osobnego brancha B1 |
| setup/docker | Szkielety Docker/Compose | Uzupełniono healthchecki i diagnostykę |
| db/schema | Migracje B2, już scalone do main | Backend pasuje do rzeczywistego schematu |
| frontend/map | Mapa, kolorowanie, filtry, panel | Osobny branch FE; integracja przez kontrakt |
| ai/service | Podsumowania, tryb mock/model, analiza nawierzchni | Osobny branch AI |
| backend/routing | ORS/mock, ranking tras i testy | Osobny branch AI; wymaga połączenia Settings/routerów |

Wszystkie branche pobrane jako origin/*. B1 realizuje swoje zadania na jednym
osobnym branchu użytkownika zgodnie z jego poleceniem. Kod pozostałych ról poza
scalonymi migracjami pozostaje na ich branchach.

## Wykonane B1

- JWT Supabase ES256/RS256 (JWKS) i HS256 (Auth API), profile /me i rola admin.
- Odcinki GeoJSON, bbox i filtry, limit 2000, najbliższy odcinek <=50 m,
  szczegóły wraz z ocenami wg pory dnia, przeszkodami i liczbą widocznych zdjęć.
- Oceny 1–5; domyślna pora dnia i dzień wg Warszawy; atomowy UPSERT 201/200.
- Widoczne komentarze, paginacja, dodawanie, moderacja admin i usuwanie cache AI.
- Limity prób zapisu, walidacja Pydantic, błędy zgodne z kontraktem, CORS.
- Pula DB z SSL, timeout i transakcjami kończonymi przed odpowiedzią HTTP.
- Health DB/AI/konfiguracji tras, Compose healthcheck wszystkich usług.
- CLAUDE.md, pięć skilli Stan/TODO, naprawiony hook SessionStart i lokalna rola B1.
- MCP Supabase read-only, verify_env.py, skrypt administratora tylko dla dev.
- Lokalny .env przygotowany z szablonu, z wygenerowanym INTERNAL_API_KEY.
  Pozostałe klucze i hasło DB uzupełnia się lokalnie; plik ignorowany przez git.

## Weryfikacja

- 45 testów API/JWT/walidacji/uprawnień/limitów/czasu: PASS.
- pip check oraz kompilacja Python: PASS.
- 22 faktyczne zapytania Repository: EXPLAIN na online Supabase, PASS.
  Plany INSERT/UPDATE/DELETE sprawdzono bez wykonywania zapisów.
- Publiczny odczyt odcinków i GeoJSON/PostGIS oraz dzień lokalny Warszawy:
  sprawdzone read-only w Supabase.
- Hook Node rozpoznaje Howoo/B1; obsługuje plik roli UTF-8 z BOM na Windows.
- Docker Desktop uruchomiony, Compose config --quiet: PASS.
- Docker Compose build backend (Python 3.12): PASS.
- Test API w kontenerze: OpenAPI 200, brak tokenu 401, brak DB health 503 — PASS.

Testy API używają fixture repozytorium. EXPLAIN sprawdza schemat i plan, lecz
nie potwierdza realnego UPSERTu, współbieżności ani zapisu z tokenem użytkownika.
Te próby wymagają SUPABASE_DB_URL, konta Auth i odcinków seed.

## Dalej

1. Uzupełnić lokalny .env: klucze projektu Supabase, URL poolera z hasłem DB,
   VITE_SUPABASE_ANON_KEY i ewentualnie ORS_API_KEY. Nie wklejać sekretów do czatu.
2. B2 seeduje Kraków. Uruchomić python scripts/verify_env.py --start.
3. Sprawdzić prawdziwe logowanie, zapis oceny 201 i zastąpienie 200, komentarz,
   uprawnienia moderacji i widoczność świeżych statystyk na mapie.
4. W Claude Code /mcp: OAuth Supabase i weryfikacja Context7. Skonfigurowane MCP
   w repo i dostęp przez plugin w tej sesji są osobnymi połączeniami.
5. Połączyć branche FE/AI/B2. Przy scalaniu backend/routing nie nadpisywać core,
   lifespan, pól Supabase ani error handlers; ORS key w Settings to SecretStr.
6. Zastąpić limiter magazynem współdzielonym przed uruchomieniem wielu workerów.
7. Właściciel repo ustawia ochronę main w GitHub. Dostępne narzędzia pluginu GitHub
   w tej sesji pozwalają na odczyt, nie na zmianę ustawień administracyjnych repo.

Kontrakt pozostał bez zmian. Nie utworzono administratora ani danych w online
Supabase. Nie wykonano commita ani push zmian B1; publikacja według reguł CLAUDE.md.
