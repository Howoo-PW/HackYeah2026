# Dziennik AI — serwis AI + backend

Najnowsze wpisy na górze. Szablon: [README.md](README.md).

<!-- wpisy -->

## 2026-10-05 — prukasz — gałąź `ai/fragments` (seed stref)

**Zadanie:** dane demo w trzech strefach wokół Rynku: centrum (ruch duży, widoki ładne, mało parkingu, dobra nawierzchnia), donut (ruch średni, brzydko, parking OK, nawierzchnia bardzo dobra), obwarzanek (nawierzchnia średnia i słaba, dużo parkingu, widoki średnie i słabe).

**Zrobione:**
- `scripts/seed_zones.py` (`--dry-run`, `--apply`, `--remove`): strefy < 1,5 km, 1,5–4 km, > 4 km od Rynku, miękkie granice (±0,35 km), stały "charakter" odcinka plus szum oceniającego, pory dnia (w nocy gorsze widoki i bezpieczeństwo, mniejszy ruch, łatwiejszy parking)
- migracja `ratings.seed_tag`: dane syntetyczne są oznaczone `zones-2026-10` i da się je usunąć (`--remove`); istniejące oceny nie zostały ruszone (sprawdzane w transakcji)
- na bazie: 42 691 ocen na 9 542 odcinkach, 2 odcinki ocen na fragment, 3–6 ocen na odcinek; teraz wszystkie 22 664 odcinki mają wynik efektywny
- średnie ocen: centrum ruch 1,8, parking 1,9, widoki 4,0, nawierzchnia 4,2; donut widoki 1,8, nawierzchnia 4,5; obwarzanek nawierzchnia 2,35, parking 4,5

**Dalej / blokery:**
- wynik efektywny jest ściągany do średniej typu drogi (cała Polska zgodnie z danymi), więc centrum wychodzi łagodniej niż same oceny (widoki 3,4 zamiast 4,0); do rozważenia lokalny prior zamiast globalnego
- bezpieczeństwo nie było w zleceniu: ustawione na 3,4 / 3,5 / 2,8 (w skrypcie do zmiany)
- stare, losowe oceny z poprzedniego seedu (1 995, 400 odcinków) zostały; usunięcie wymaga zgody autora


## 2026-10-05 — prukasz — gałąź `ai/fragments`

**Zadanie:** jednostki oceny po 300–500 m zamiast kawałków po kilkadziesiąt metrów; cięcie tylko na ważnych skrzyżowaniach; krótsze łączone z sąsiadem; baza i routing spójne z nowym podziałem.

**Zrobione:**
- `build_fragments` (`backend/app/grouping.py`): łańcuchy jednej ulicy cięte na skrzyżowaniach z drogami primary/secondary/tertiary po min. 300 m (limit 700 m), fragmenty krótsze niż 300 m łączone z sąsiadem (najpierw ta sama ulica, potem dowolny; limit 900 m); sąsiedztwo także dla skrzyżowań T znalezionych w geometrii
- wynik na bazie: 22 664 odcinki → **5 053 fragmenty** (było 10 303), mediana 534 m, 3,8% długości dróg w fragmentach < 300 m (izolowane drogi)
- zastosowane w jednej transakcji (`scripts/build_segment_groups.py --apply`), odświeżone `segment_scores` (2 289 odcinków z wynikiem, było 1 468) i `routing_graph`
- widok `routing_edge_group` (krawędź grafu → fragment); trasa 14,5 km = 33 fragmenty zamiast 194 krawędzi
- celowo **nie** skracałem grafu routingu: węzły na małych skrzyżowaniach są potrzebne do skrętu; routing 0,2–0,7 s, więc nie ma potrzeby go odchudzać
- 11 testów fragmentów (cięcie, scalanie, limity, determinizm); testów backendu/UI nie uruchamiałem na prośbę

**Dalej / blokery:**
- ok. 2/3 krawędzi grafu nie ma odcinka, więc nie ma fragmentu (drogi serwisowe itp.); oceny dla nich to priory z tagów OSM
- fragment łączy czasem różne ulice (np. krótka uliczka z sąsiednią): `from_street`/`to_street` są wtedy puste
- jedna ocena rozchodzi się teraz na ok. 500 m: do oceny po stronie UI, czy "tylko ten kawałek" jest potrzebne


## 2026-10-04 — prukasz — gałąź `ai/llm-openrouter`

**Zadanie:** pierwsze prawdziwe wywołanie LLM w serwisie AI (dotąd tylko mock).

**Zrobione:**
- model: `stealth/space-bunny-alpha` przez OpenRouter (API zgodne z OpenAI, darmowy podgląd), konfiguracja tylko w `.env`
- odkryte w teście: domyślne `with_structured_output` nie działa (model zwraca własne klucze albo markdown, 0/3 poprawnych), a pojedyncza odpowiedź trwała 7–21 s
- poprawka: `AI_STRUCTURED_METHOD=json_mode` (schemat opisany w prompcie, `schema_hint`) i `AI_REASONING_EFFORT=low`: 3/3 poprawnych, ok. 4–5 s (limit w kontrakcie to 15 s)
- sprawdzone przez HTTP na kontenerze: polecenie wstrzyknięte w komentarzu zostało zignorowane
- porównanie modeli (OpenRouter, 9 darmowych): Space Bunny Alpha 3/3 w 2,7 s, Laguna S 2.1 3/3 w 4,9 s; reszta wolniejsza lub z błędami schematu
- **OpenAI (klucz własny, budżet 4 USD): wybrany `gpt-5.4-nano` z `AI_REASONING_EFFORT=none`**: 3/3 na realistycznym przypadku, ok. 1,5 s, ok. $0,0003 za wywołanie (ok. 13 tys. wywołań za 4 USD). `gpt-5-nano` w trybie `minimal` odrzucony: 0/3, za każdym razem gubi nawierzchnię i widoki (`brak informacji`); w trybie `low` poprawny, ale 9 s
- modele gpt-5 przyjmują `reasoning_effort` i odrzucają `temperature`: `_model()` rozróżnia OpenAI natywne od bramek (OpenRouter: `extra_body`)
- 7 nowych testów konfiguracji (bez sieci), razem 17

**Dalej / blokery:**
- jakość: model dopisuje wnioski spoza komentarzy (np. `safety` z samych dziur) i wpisuje do `conflicts` różnice pory dnia, które nie są sprzecznością; do dopracowania w prompcie
- `/analyze-surface` (zdjęcia) nieprzetestowane na prawdziwym modelu
- stealth = anonimowy dostawca, możliwe logowanie zapytań i zniknięcie modelu; klucz OpenRouter zostaje w `.env` jako `OPENROUTER_API_KEY` (zapas), przełączenie to 4 linijki w `.env`
- koszt: ustawić twardy limit wydatków w koncie OpenAI; backend cache'uje streszczenia w `segment_summaries`, więc AI woła się tylko przy zmianie komentarzy
- klucz OpenAI też trafił do rozmowy: po hackathonie unieważnić
- klucz OpenRouter trafił do rozmowy: zalecana rotacja po hackathonie


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
