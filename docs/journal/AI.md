# Dziennik AI — serwis AI + backend

Najnowsze wpisy na górze. Szablon: [README.md](README.md).

<!-- wpisy -->

## 2026-10-04 — prukasz — gałąź `backend/segment-groups`

**Zadanie:** połączyć krótkie odcinki w grupy ocenialne przez użytkownika i dać każdemu odcinkowi wynik także wtedy, gdy ocenili tylko sąsiadów.

**Zrobione:**
- diagnoza na bazie: mediana odcinka 89 m, 53% krótszych niż 100 m, ocenionych tylko 400 z 22 664 (1,8%)
- `backend/app/grouping.py`: `build_groups` (łańcuchy tej samej ulicy po węzłach, grupy ~500 m, nazwy ulic na końcach) i `effective_scores` (własne oceny → grupa → średnia typu drogi, `confidence`)
- `scripts/build_segment_groups.py` generuje seed `supabase/seed/groups_*.sql`: 22 664 odcinków → 10 303 grup, tylko 6% długości dróg w grupach krótszych niż 100 m
- migracja `20261004120000_segment_groups.sql` (tabela `segment_groups`, `segments.group_id`, RLS), sprawdzona na prawdziwej bazie w transakcji z wycofaniem
- API: `scores` efektywne, nowe `scores_own`, `scores_source`, `confidence`, `group`, endpoint `GET /groups/{id}`; kontrakt uzupełniony
- 90 testów backendu (22 nowe)
- nazwy wersji migracji w bazie to znaczniki czasu z narzędzia (nie takie jak nazwy plików), treść ta sama

**Dalej / blokery:**
- zastosowane na wspólnej bazie (2026-10-04): `segment_groups` + seed grup, `segment_scores` (wynik efektywny w SQL, 0 rozbieżności z Pythonem na 22 664 odcinkach), `pgrouting` 3.4.1
- `osm_ways` (zastosowana + załadowana): sieć OSM dla auta i roweru, 58 370 dróg, kierunki per profil, id węzłów OSM; `osm_access.py` (66 testów), `scripts/load_osm_routing.py`; spójność po węzłach: auto 97,3%, rower 96,4% długości w jednej składowej
- B2: stan bazy i zalecenia do grafu w `docs/ROUTING_DB_STATE.md`; `scripts/check_graph.py` testuje spójność (graf z `segments`: największa składowa 74%, po węzłach T 96%)
- filtry `min_score`/`rated_only` działają już po limicie 2000 odcinków
- FE: kolor szacunku jaśniejszy, klik podświetla grupę (`GET /groups/{id}`), podpis „na podstawie N ocen"
- oceny „tylko ten kawałek" vs „cała ulica" wymagają osobnej zmiany (zakres oceny)
- po ponownym imporcie OSM trzeba przebudować grupy (ids odcinków się przesuną)




## 2026-10-03 — prukasz — gałąź `backend/routing`

**Zadanie:** auto-routing `POST /api/v1/route` niezależnie od reszty zespołu (bez bazy i B1).

**Zrobione:**
- `backend/app/routing/`: dostawcy tras (OpenRouteService + mock), `SegmentSource` (na razie dane przykładowe z pliku), ocena i ranking tras, walidacja obszaru Krakowa
- błędy w formacie kontraktu (`backend/app/errors.py`), `routing` w `/health`
- 21 testów (pytest, Python 3.12 w kontenerze), sprawdzone na żywo w Compose
- odkryte w testach: odcinki rozchodzące się pod małym kątem wpadały do wyniku → odcinek liczy się, gdy ≥ 50% jego długości leży w buforze 15 m

**Dalej / blokery:**
- klient ORS **niesprawdzony na prawdziwym API** (brak klucza): format żądania z `alternative_routes` według znanej dokumentacji, testy tylko na podstawionych odpowiedziach
- B2: implementacja `SegmentSource` na PostGIS; B1: ten sam `errors.py` może się zderzyć z ich wersją przy scalaniu
- `score` w odpowiedzi bywa `null` (brak ocen na trasie) — kontrakt tego nie przewiduje, wymaga PR do `docs/CONTRACT.md`

## 2026-10-03 — prukasz — gałąź `ai/service`

**Zadanie:** serwis AI zgodny z kontraktem: `/summarize` i `/analyze-surface`, tryb mock, LangChain.

**Zrobione:**
- endpointy `/health`, `/summarize`, `/analyze-surface`; autoryzacja `X-Internal-Key`; błędy w formacie kontraktu (401, 422, 502)
- tryb mock (domyślny) i ścieżka LangChain (`app/llm.py`, `init_chat_model` + `with_structured_output`), prompt z ochroną przed wstrzykiwaniem poleceń
- 10 testów (pytest w kontenerze) — przechodzą; sprawdzone na żywo w Compose

**Dalej / blokery:**
- wybrać dostawcę i model, dodać klucz do `.env` i przetestować prawdziwe podsumowania po polsku
- integracja w backendzie (`backend/ai-integration`) po `backend/core` od B1
## 2026-10-03 — prukasz — gałąź `setup/docker`

**Zadanie:** postawić Docker Compose ze szkieletami wszystkich usług, zanim zespół zacznie pracę.

**Zrobione:**
- `docker-compose.yml`: frontend (5173), backend (8000), ai (8001→8000), healthchecki, hot reload
- szkielety: backend `/api/v1/health` (sprawdza AI), ai `/health` (tryb mock), frontend Vite + React + TS + Tailwind z ekranem stanu usług
- `.env.example`, `README.md`; sprawdzone: wszystkie kontenery healthy, CORS, build frontendu, przeładowanie po zmianie kodu

**Dalej / blokery:**
- PR `setup/docker` → `main`, potem gałąź `ai/service`: `/summarize` (mock → LangChain)
