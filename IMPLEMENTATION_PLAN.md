# Rate My Road — plan implementacji

Źródła: [brief.md](brief.md) (zakres produktu) i [plan.md](plan.md) (wymagania techniczne i zasady pracy).

## 0. Założenia i otwarte pytania

| Temat | Decyzja |
|---|---|
| Frontend | React + Vite + **TypeScript** + **Tailwind CSS** (potwierdzone) |
| Telefon | Frontend jako **PWA** (instalowalna na telefonie, geolokalizacja, układ mobile-first) |
| Baza | Tylko **Supabase online (Postgres + PostGIS)**. Brak lokalnej bazy i trybu offline (potwierdzone) |
| Projekt Supabase | `HackYeah2026`, ref `lsfpirkqdtjkcaujnsde`, region `eu-central-1`, Postgres 17. Na 2026-10-03: brak tabel, PostGIS 3.3.7 i pgRouting 3.4.1 dostępne, ale niewłączone (włącza migracja w `db/schema`) |
| Zdjęcia | Zdjęcia użytkowników w **Supabase Storage**, w bazie tylko metadane (tabela `segment_photos`) |
| Auto-routing | W zakresie: trasy z zewnętrznego silnika (OpenRouteService lub OSRM) i ranking wg naszych ocen (sekcja 4) |
| Obszar | Tylko **Kraków**: bbox `49.967,19.792,50.126,20.217` (S,W,N,E) |
| Wymiary ocen | nawierzchnia, widoki, bezpieczeństwo, obciążenie/problemy, parkingi; skala 1–5 |
| Zespół | 4 osoby, podział w sekcji 8 |
| Poza MVP | automatyczna ocena nawierzchni ze zdjęć (opcjonalnie, jeśli osoba od AI ma czas) |

Stan gita na dziś (2026-10-03): katalog **nie jest repozytorium** — zawiera tylko `brief.md` i `plan.md`. Narzędzia lokalne: git 2.55, Docker 29.8, Python 3.14, Node 24.

## 1. Architektura

```
[PWA: React/Vite]  ──HTTP──▶  [backend: FastAPI]  ──HTTP──▶  [ai-service: FastAPI]
   kontener: frontend            kontener: backend               kontener: ai
        │                             │                               │
        └── Supabase Auth (login) ────┤                               └──▶ dostawca LLM (dowolny, z .env)
                                      ├──▶ Supabase (Postgres + PostGIS, Storage na zdjęcia)
                                      └──▶ silnik tras (OpenRouteService / OSRM)
```

- Każda usługa w osobnym kontenerze, spięte przez `docker-compose.yml`.
- Frontend używa Supabase **tylko do logowania** (klucz `anon`). Dane czyta i zapisuje przez backend.
- Backend jako jedyny ma klucz `service_role`. Serwis AI nie ma dostępu do bazy: dostaje dane w żądaniu i zwraca wynik.

## 2. Struktura repozytorium

```
/
├── CLAUDE.md                     # główne instrukcje dla Claude, wymusza ładowanie skilla overview
├── README.md                     # uruchomienie dla ludzi
├── docker-compose.yml
├── .env.example                  # lista zmiennych, bez wartości
├── docs/
│   ├── CONTRACT.md               # wspólny kontrakt: API, typy, enumy, porty
│   ├── MAP_STACK.md              # biblioteki i usługi mapowe, limity, dokumentacja
│   └── journal/                  # dziennik pracy: FE.md, B1.md, B2.md, AI.md
├── .gitignore                    # .env, node_modules, __pycache__, dist
├── .claude/
│   ├── settings.json             # bez atrybucji Claude w commitach/PR, hook SessionStart, uprawnienia
│   └── skills/
│       ├── project-overview/SKILL.md   # nadrzędny
│       ├── database/SKILL.md
│       ├── backend/SKILL.md
│       ├── ai/SKILL.md
│       └── frontend/SKILL.md
├── supabase/
│   ├── migrations/               # SQL: schemat, RLS, widoki
│   └── seed/                     # seed.sql + dane Krakowa z OSM
├── scripts/
│   ├── import_osm.py             # Overpass → odcinki i parkingi Krakowa
│   └── verify_env.py             # weryfikacja środowiska po klonowaniu
├── backend/                      # Python, FastAPI
├── ai-service/                   # Python, FastAPI
└── frontend/                     # React, Vite, TS, Tailwind, PWA
```

## 3. Struktura danych (Supabase)

Wszystkie geometrie w `SRID 4326`. Indeksy GiST na kolumnach `geom`.

| Tabela | Kolumny (najważniejsze) | Uwagi |
|---|---|---|
| `profiles` | `id` (= `auth.users.id`), `display_name`, `created_at` | Tworzony triggerem po rejestracji |
| `segments` | `id`, `osm_way_id`, `name`, `highway`, `surface_osm`, `smoothness_osm`, `maxspeed`, `lit`, `geom LINESTRING`, `length_m` | Seed z OSM. Długie drogi dzielone na odcinki ≤ 300 m |
| `ratings` | `id`, `segment_id`, `user_id`, `surface`, `views`, `safety`, `traffic`, `parking` (każde `smallint 1–5`, null = brak oceny), `time_of_day` (`morning/day/evening/night`), `created_at` | Ograniczenie: 1 ocena na użytkownika na odcinek na dobę |
| `comments` | `id`, `segment_id`, `user_id`, `text` (≤ 1000 znaków), `status` (`visible/hidden`), `created_at` | Admin może ukryć |
| `obstacles` | `id`, `segment_id`, `type` (`roadwork/closure/pothole/other`), `description`, `geom POINT`, `reported_by`, `valid_until`, `status` | Wygasają po `valid_until` |
| `parking_spots` | `id`, `osm_id`, `name`, `capacity`, `fee`, `geom POINT` | Seed z OSM (`amenity=parking`) |
| `segment_photos` | `id`, `segment_id`, `user_id`, `storage_path`, `taken_at`, `status` (`visible/hidden`), `ai_surface jsonb` (opcjonalnie), `created_at` | Pliki w bucket `segment-photos` w Supabase Storage, nie w tabeli |
| `segment_summaries` | `segment_id`, `summary jsonb`, `comments_count`, `model`, `updated_at` | Cache AI. Przeliczany po ≥ 5 nowych komentarzach |
| `segment_stats` (widok materializowany) | `segment_id`, średnie 5 wymiarów, `ratings_count`, `last_rating_at` | Do kolorowania mapy, odświeżany cyklicznie |

Role: **w `auth.users.app_metadata.role`** (`user` / `admin`), nie w `user_metadata` — tę drugą użytkownik może sam zmienić.

RLS włączone na wszystkich tabelach. Odczyt publiczny dla `segments`, `parking_spots`, `segment_stats`, widocznych komentarzy. Zapis tylko przez backend (`service_role`).

## 4. API

Wszystkie endpointy, formaty, enumy, porty i limity są w **[docs/CONTRACT.md](docs/CONTRACT.md)** — to jedyne źródło prawdy. Tutaj tylko opis działania tego, czego kontrakt nie obejmuje.

Backend udostępnia dokumentację OpenAPI pod `/docs`. Musi się zgadzać z kontraktem.

**Auto-routing** — silniki tras nie znają naszych ocen, więc:
1. Backend pobiera z silnika 2–3 trasy alternatywne (OpenRouteService z darmowym kluczem albo publiczny serwer demo OSRM — oba z limitami, wystarczą na demo; sprawdzić aktualne warunki).
2. Dopasowuje każdą trasę do odcinków w bazie (PostGIS: odcinki w buforze kilku metrów od linii trasy).
3. Liczy wynik trasy: średnia ocen ważona długością odcinków i wagami użytkownika.
4. Zwraca trasy posortowane wg wyniku, z oceną dla każdej.

**Serwis AI — dowolny dostawca**
- Model wybierany przez `.env` (`AI_PROVIDER`, `AI_MODEL`, `AI_API_KEY`), bez zmian w kodzie.
- LangChain tylko w minimalnym zakresie: `init_chat_model` (wybór dostawcy) i `with_structured_output` (odpowiedź jako model Pydantic z kontraktu). Bez łańcuchów i agentów.
- Cała logika LangChain w jednym pliku `ai-service/app/llm.py`, reszta serwisu go nie importuje.
- Na start darmowy plan dostawcy (np. Gemini, Groq, OpenRouter). Sprawdzić aktualne limity przed demo.

Prawdziwe wyznaczanie trasy po naszych wagach (własny GraphHopper/Valhalla z danymi Krakowa) — dopiero po hackathonie.

## 5. Bezpieczeństwo

**Konta użytkowników**
- Rejestracja i logowanie przez Supabase Auth (e-mail + hasło, opcjonalnie Google).
- Frontend wysyła JWT w nagłówku `Authorization: Bearer`. Backend weryfikuje podpis (JWKS Supabase), ważność i rolę.
- Limity zapisów: np. 30 ocen i 10 komentarzy na godzinę na użytkownika.
- Walidacja wejścia w Pydantic, długość komentarzy, zakres ocen, współrzędne tylko w bbox Krakowa.

**Konta dev i admin**
- Rola `admin` nadawana ręcznie w Supabase (SQL lub panel), nigdy przez API.
- Konto admina do testów tworzone skryptem tylko w środowisku `dev`. Hasło w `.env`, nie w repo.
- Endpointy `/admin/*` sprawdzają rolę po stronie backendu, niezależnie od UI.

**Sekrety i usługi**
- Wszystkie sekrety w `.env` (w `.gitignore`). W repo tylko `.env.example`.
- `SUPABASE_SERVICE_ROLE_KEY` i `AI_API_KEY` nigdy nie trafiają do frontendu (zmienne `VITE_*` są publiczne).
- Backend ↔ AI: wspólny sekret w nagłówku `X-Internal-Key`. Kontener AI bez publicznego portu w produkcji.
- CORS backendu tylko dla adresu frontendu.
- Zdjęcia: sprawdzanie typu i rozmiaru, usuwanie metadanych EXIF (w tym GPS), bucket prywatny z podpisanymi URL-ami, admin może ukryć zdjęcie.
- Komentarze traktowane w prompcie jako dane, nie instrukcje. Odpowiedź modelu walidowana schematem.

**Zmienne `.env`**

```
# wspólne
APP_ENV=dev
# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_DB_URL=
# backend
CORS_ORIGINS=http://localhost:5173
AI_SERVICE_URL=http://ai:8000
INTERNAL_API_KEY=
ROUTING_PROVIDER=ors
ORS_API_KEY=
DEV_ADMIN_EMAIL=
DEV_ADMIN_PASSWORD=
# ai-service
AI_PROVIDER=google_genai        # dowolny dostawca obsługiwany przez LangChain
AI_MODEL=gemini-2.5-flash
AI_API_KEY=
AI_BASE_URL=                    # opcjonalnie: API zgodne z OpenAI (Groq, OpenRouter, Ollama)
MOCK_AI=false
# frontend (publiczne)
VITE_API_URL=http://localhost:8000/api/v1
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
```

## 6. Skille, CLAUDE.md i dokumentacja

**Skille** w `.claude/skills/`:

| Skill | Zawartość |
|---|---|
| `project-overview` (nadrzędny) | Cel, architektura, konwencje, zasady gita, mapa pozostałych skilli, **globalny stan i TODO** |
| `database` | Schemat, migracje, RLS, seedowanie, zasady zmian schematu, stan i TODO |
| `backend` | Struktura modułów, konwencje API, auth, testy, stan i TODO |
| `ai` | Kontrakt API, prompty, ochrona przed wstrzykiwaniem, tryb mock, stan i TODO |
| `frontend` | Komponenty, mapa, PWA, styl, integracja z API, stan i TODO |

Każdy skill kończy się sekcjami **Stan** (co działa) i **TODO** (co dalej, z gałęzią). Overview zbiera skrót z pozostałych.

**Automatyczne dokumentowanie kodu** — w każdym skillu reguła: po zmianie kodu w danym obszarze Claude
1. dodaje docstringi lub komentarze JSDoc do nowych i zmienionych funkcji publicznych,
2. aktualizuje sekcje skilla, jeśli zmieniła się struktura, API lub schemat,
3. aktualizuje **Stan** i **TODO** w skillu oraz w overview.

**Wymuszenie ładowania skilla**
- `CLAUDE.md` na początku: „Przed każdą pracą załaduj skill `project-overview`, a potem skill obszaru, w którym pracujesz".
- Hook `SessionStart` w `.claude/settings.json` wypisuje przypomnienie, aktualną gałąź i stan gita, dzięki czemu reguła jest widoczna w każdej sesji.

## 7. Zasady pracy z gitem

- Przed rozpoczęciem pracy: `git status`, `git fetch`, sprawdzenie gałęzi i niezacommitowanych zmian. Zasada zapisana w overview i w hooku.
- `main` chroniony, tylko przez PR. Każdy element na osobnej gałęzi:

| Gałąź | Zakres | Właściciel |
|---|---|---|
| `setup/repo` | Repo, `.gitignore`, `.env.example`, README, `docker-compose.yml` (szkielet) | B1 |
| `docs/skills` | `CLAUDE.md`, 5 skilli, hook SessionStart | B1 |
| `db/schema` | Migracje, RLS, widoki, bucket Storage | B2 |
| `db/seed-krakow` | `import_osm.py`, pliki seed | B2 |
| `backend/core` | FastAPI, auth, moduły segments/ratings/comments | B1 |
| `backend/obstacles-parking` | Przeszkody i parkingi | B2 |
| `backend/photos` | Przesyłanie i lista zdjęć | B2 |
| `backend/routing` | `POST /route`, integracja z silnikiem tras | AI |
| `ai/service` | Serwis AI z trybem mock, potem z modelem | AI |
| `backend/ai-integration` | Wywołania AI, cache podsumowań | AI |
| `frontend/map` | Mapa, kolorowanie, filtry | FE |
| `frontend/auth-rating` | Logowanie, formularz oceny, komentarzy i zdjęć | FE |
| `frontend/routing` | Wybór A→B, suwaki wag, trasy na mapie | FE |
| `frontend/pwa` | Manifest, service worker, geolokalizacja | FE |
| `infra/verify` | `verify_env.py`, healthchecki w Compose | B1 |

## 8. Zespół i etapy implementacji

| Osoba | Rola | Odpowiada za |
|---|---|---|
| **FE** | Frontend (samodzielnie) | Cały `frontend/`, PWA, integracja z API. Do czasu gotowości backendu pracuje na mockach z kontraktu API (sekcja 4) |
| **B1** | Backend + infrastruktura | Repo, Docker Compose, skille, auth i JWT, moduły segments/ratings/comments, weryfikacja środowiska |
| **B2** | Backend + baza danych | Schemat, migracje, RLS, seed Krakowa z OSM, Storage, moduły obstacles/parking/photos, widok `segment_stats` |
| **AI** | Serwis AI + backend | `ai-service/`, integracja AI w backendzie, cache podsumowań, auto-routing, opcjonalnie ocena zdjęć |

Punkty styku uzgadniamy razem **przed utworzeniem gałęzi** w [docs/CONTRACT.md](docs/CONTRACT.md): schemat danych (B2 + wszyscy), kontrakt API (B1 + FE), kontrakt serwisu AI (AI + B1). Każdy jest właścicielem skilla swojego obszaru: FE → `frontend`, B1 → `backend` i `project-overview`, B2 → `database`, AI → `ai`.

**Etap 0 — przygotowanie**
1. `git init`, repo na GitHubie, ochrona `main`. W pierwszym commicie razem z kontraktem: `.claude/settings.json` z wyłączoną atrybucją Claude (`attribution.commit` i `attribution.pr` puste, `sessionUrl: false`), żeby każdy po sklonowaniu miał commity i PR-y bez „Co-Authored-By: Claude”.
2. Supabase MCP: zdalny serwer `https://mcp.supabase.com/mcp` w `.mcp.json` (scope `project`, commitowany, bez sekretów), z `project_ref` i `read_only=true`. Każdy loguje się swoim kontem Supabase przez `/mcp` (OAuth), więc każdy musi być członkiem projektu w Supabase. B2 (baza) może mieć lokalnie wersję z zapisem do stosowania migracji.
3. Uzupełnienie `.env` danymi Supabase (URL i klucze od organizatora).
4. **Spotkanie całego zespołu: przegląd i zatwierdzenie [docs/CONTRACT.md](docs/CONTRACT.md)** (sekcja 1 kontraktu). Dopiero potem tworzymy gałęzie. Kontrakt trafia do `main` jako pierwszy commit.

**Etap 1 — fundamenty** (`setup/repo`, `docs/skills`)
5. Szkielet repo, `.env.example`, `.gitignore`, README.
6. `CLAUDE.md`, 5 skilli z sekcjami Stan i TODO, hook SessionStart.

**Etap 2 — dane** (`db/schema`, `db/seed-krakow`)
7. Migracje: PostGIS, tabele, indeksy, RLS, trigger `profiles`, widok `segment_stats`.
8. `import_osm.py`: pobranie z Overpass dróg Krakowa (`highway` od `primary` do `residential`, plus `cycleway`) i parkingów, podział na odcinki, zapis do plików seed.
9. Seed: odcinki, parkingi, przykładowe oceny i komentarze do demo, konto admina tylko w dev.

**Etap 3 — backend i AI równolegle** (`backend/core`, `ai/service`)
10. Backend: konfiguracja, połączenie z bazą, weryfikacja JWT, `/health`, endpointy segmentów, ocen i komentarzy, testy.
11. Serwis AI: `/health`, `/summarize` w trybie mock, potem z modelem, testy na polskich komentarzach.

**Etap 4 — frontend** (`frontend/map`, `frontend/auth-rating`)
12. Vite + React + TS + Tailwind, mapa: MapLibre GL JS + react-map-gl + kafelki OpenFreeMap (szczegóły i wersje w [docs/MAP_STACK.md](docs/MAP_STACK.md)), atrybucja „© OpenStreetMap contributors".
13. Kolorowanie odcinków wg wybranego wymiaru, filtr, panel szczegółów.
14. Logowanie (Supabase Auth), ocena, komentarze, podsumowanie AI.

**Etap 5 — uzupełnienia** (`backend/obstacles-parking`, `backend/photos`, `backend/ai-integration`, `backend/routing`, `frontend/routing`, `frontend/pwa`)
15. Przeszkody i parkingi na mapie.
16. Zdjęcia odcinków: przesyłanie do Storage, galeria w panelu odcinka.
17. Cache podsumowań AI, przeliczanie w tle.
18. Auto-routing: trasy alternatywne z silnika, ranking wg ocen, wybór wag w UI.
19. PWA: manifest, ikona, geolokalizacja („oceń drogę, na której stoję" — nie podczas jazdy).
20. Opcjonalnie: `/analyze-surface` na zdjęciach z bazy.

**Etap 6 — weryfikacja i demo** (`infra/verify`)
21. `verify_env.py` i healthchecki (sekcja 9).
22. Dane demo, zamrożenie kodu, próba prezentacji.

Zależności: Etap 2 musi poprzedzać pełną integrację backendu, ale backend, AI i frontend mogą ruszyć równolegle na danych mock, gdy schemat i API (sekcje 3–4) są zatwierdzone.

## 9. Weryfikacja środowiska po klonowaniu

`python scripts/verify_env.py` sprawdza i wypisuje ✅/❌ z podpowiedzią naprawy:

1. Wersje narzędzi: git, Docker, Docker Compose, Python, Node.
2. Istnienie `.env` i komplet zmiennych z `.env.example` (bez wypisywania wartości).
3. Połączenie z Supabase i obecność PostGIS oraz tabel z migracji.
4. Dostępność MCP Supabase i Context7 (`claude mcp list`).
5. Obecność `CLAUDE.md` i 5 skilli.
6. `docker compose up -d`, następnie `GET /health` dla backendu i AI oraz odpowiedź frontendu.
7. Stan gita: aktualna gałąź, niezacommitowane zmiany, różnica z `origin/main`.

## 10. Wymagania: narzędzia, biblioteki i MCP

**Narzędzia lokalne** (sprawdza `verify_env.py`):

| Narzędzie | Wersja minimalna |
|---|---|
| git | 2.40 |
| Docker + Docker Compose v2 | Docker 24 |
| Node.js | 24 LTS |
| Python | 3.12 (w kontenerach przypięty obraz, np. `python:3.12-slim`) |
| Claude Code | aktualna |

**Biblioteki:** wersje i licencje w [docs/MAP_STACK.md](docs/MAP_STACK.md). W `package.json` i `requirements.txt` przypinamy wersje (`^` w npm dla wersji pobocznych, `==` w Pythonie po pierwszej działającej instalacji).

**Serwery MCP:**

| MCP | Status | Konfiguracja | Do czego |
|---|---|---|---|
| **Context7** (Upstash) | Wymagany | `.mcp.json` w repo, włączony automatycznie przez `enabledMcpjsonServers` | Aktualna dokumentacja bibliotek: MapLibre, react-map-gl, Supabase, FastAPI, LangChain, Tailwind, Vite |
| **Supabase** (oficjalny) | Wymagany | `.mcp.json` po podaniu `project_ref` (krok 2 Etapu 0), logowanie przez `/mcp` | Schemat, zapytania, migracje |
| GitHub | Nie | Zamiast MCP: `gh` CLI | PR-y, issues |
| Mapy, OSM, Overpass, ORS | Nie | — | Brak oficjalnych serwerów. Istnieją tylko projekty społecznościowe (np. `maplibre_mcp`, kilka `osm-mcp`, `openroute-mcp` 0.0.4) — niezweryfikowany kod uruchamiany na komputerach zespołu, a zapytania OSM zużywają limity publicznych serwerów. Zamiast tego: Context7 + Overpass Turbo w przeglądarce |

Zasada: dodajemy tylko MCP od producenta usługi albo szeroko używane (jak Context7). Nowy MCP = PR ze zmianą `.mcp.json` i tej tabeli.

## 11. Postęp

Szczegółowy stan i TODO prowadzone są w skillach (sekcja 6). Ten plan aktualizujemy tylko przy zmianie zakresu.

| Etap | Stan |
|---|---|
| 0. Przygotowanie | 🔄 kontrakt zatwierdzony 2026-10-03; zostaje ochrona `main` i dostęp do Supabase dla zespołu |
| 1. Fundamenty | ⏳ |
| 2. Dane | ⏳ |
| 3. Backend i AI | ⏳ |
| 4. Frontend | ⏳ |
| 5. Uzupełnienia | ⏳ |
| 6. Weryfikacja i demo | ⏳ |
