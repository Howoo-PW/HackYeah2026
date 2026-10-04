# Dziennik FE — frontend

Najnowsze wpisy na górze. Szablon: [README.md](README.md).

<!-- wpisy -->

## 2026-10-04 — Beata — gałąź `feature/ai-assistant` (poprawki asystenta, seed Wisły)

**Zrobione:**
- Plan AI: „wzdłuż Wisły / przez Planty / przez ulicę X” daje 1–3 konkretne punkty pośrednie (`via_places`); backend pomija punkt pośredni, którego nie znajdzie (błąd tylko dla startu i celu).
- Panel asystenta: (przyciski „Dodaj punkt startowy / końcowy” dodane, a potem usunięte na prośbę); w trasie od asystenta przycisk „Zapytaj ponownie”.
- Seed `scripts/seed_vistula.py` (tag `vistula-2026-10`): 84 odcinki nad Wisłą (bulwary, Bulwarowa, Podgórska/Konopnickiej przy bulwarze), 249 ocen i 30 komentarzy w stylu „fajna droga wzdłuż Wisły”. Cofnięcie: `python scripts/seed_vistula.py --remove`. Migracja `20261008120000_comments_seed_tag.sql` (kolumna `comments.seed_tag`) zastosowana na bazie online.

- Trasy „wzdłuż Wisły”: model ustawia tylko `along_river`, a backend sam wybiera 1–3 punkty z bulwarów w bazie (`assistant_river.py`, `osm_ways` „Bulwar …”) tak, żeby prawie nie wydłużały drogi start→cel, w kolejności jazdy i osiągalne dla profilu (≤150 m od drogi); punkty nieosiągalne (np. ścieżka dla auta) są pomijane. Bez środka transportu i przy bulwarach/rzece profil to rower. Testy: `backend/tests/test_assistant_river.py`.

- Wyszukiwanie po sensie komentarzy (pgvector): migracja `20261008130000_comment_embeddings.sql` (tabela `comment_embeddings`, 1536 wymiarów, HNSW, RLS bez polityk), `POST /embed` w serwisie AI (`text-embedding-3-small`), `backend/app/embeddings.py` (nowy komentarz embedowany w tle), `scripts/embed_comments.py` (uzupełnienie: 1100 komentarzy zrobione). Plan AI ma pole `topic`; opis słowami („spokojna droga nad wodą”) szuka fragmentów ulic po podobieństwie komentarzy (`do_streets_by_meaning`), kryterium z pięciu wymiarów nadal liczy oceny.

**Dalej / blokery:**
- Bulwary (ścieżki) w większości nie są w tabeli `segments`, więc nie da się ich ocenić ani wybrać autem; seed objął te, które są.
- Test pominiętego punktu pośredniego w backendzie i dokumentacja skilli do dopisania.

## 2026-10-04 — Beata — gałąź `feature/ai-assistant`

**Zadanie:** wyszukiwarka tras i miejsc z opisu słowami, z agentem AI, który korzysta z ocen, komentarzy i danych (docs/ASSISTANT.md).

**Zrobione:**
- Serwis AI: `POST /assistant/plan` (opis → plan route/place/streets, profil, wagi 0–3) i `POST /assistant/answer` (fakty → odpowiedź); tryb mock z regułami; prompty z osobnymi wskazówkami dla trasy, miejsca i ulic.
- Backend: `POST /api/v1/assistant` (10/min na IP). Potok bez pętli narzędzi: plan z AI → geokodowanie Nominatim (cache, 1 zapytanie/s, obrys dzielnicy) → trasa z własnego grafu / miejsce / ranking fragmentów → fakty słowami (oceny, komentarze, podsumowania, przeszkody) → odpowiedź AI. Błąd AI przy odpowiedzi: pokazujemy fakty (`model: fallback`).
- Frontend: przycisk „Asystent AI”, `AssistantPanel`; trasa trafia do planera (`route.load` + `plan.adopt`, notatka asystenta w `RoutePanel`), miejsce na kartę miejsca, ulice jako numerowane pinezki z podświetleniem.
- Testy: AI 43, backend 332 (w tym 41 asystenta); SQL sprawdzony na bazie (tylko odczyty); test w przeglądarce: trasa, ulice, miejsce, prośba spoza zakresu.

**Dalej / blokery:**
- Kontrakt: `POST /assistant` i `/assistant/*` serwisu AI do dopisania do `docs/CONTRACT.md` osobnym PR (na razie opis w docs/ASSISTANT.md).
- Opóźnienie 5–12 s (dwa wywołania modelu + geokodowanie + trasa); streaming odpowiedzi skróciłby czekanie.
- „Moja lokalizacja” w opisie nie jest obsługiwana; punkt startu trzeba podać.

## 2026-10-04 — Beata — gałąź `frontend/map-cache`

**Zadanie:** mapa ma się ładować szybciej przy przesuwaniu: bufor (cache) i doczytywanie obszaru z wyprzedzeniem.

**Zrobione:**
- `src/map/useMapData.ts`: dane mapy w kafelkach (siatka 0,03° x 0,02°), cache w pamięci kluczowany filtrem i wersją danych; najpierw kafelki pod widokiem, potem pierścień wokół niego (doczytywanie w tle, do 4 równoległych zapytań); powrót w już wczytany obszar jest natychmiastowy.
- Przy oddaleniu (fragmenty ulic) jedno zapytanie na całe miasto, potem z pamięci.
- Kafelek, który backend odrzuca limitem 2000 odcinków (422), jest dzielony na 4 i scalany; duplikaty z granic kafelków usuwane; stare dane zostają widoczne do czasu wczytania nowych (bez mrugania pustą mapą); limit 90 kafelków w pamięci.
- Zapisanie oceny (`OPINIONS_CHANGED`) unieważnia cache.
- Pomiar w przeglądarce: start 1 zapytanie (fragmenty), po przybliżeniu 12 (widok + otoczenie), po przesunięciu tylko kolejne 4 w tle, bez pustych obszarów.

**Dalej / blokery:**
- Nagłówki cache po stronie backendu (ETag / Cache-Control dla `/segments`) przyspieszyłyby też pierwsze wczytanie (B1).



## 2026-10-04 — Beata — gałąź `frontend/routing`

**Zadanie:** sprawdzić uruchomienie w Dockerze; widok wyboru trasy A→B z opcjami (sam wybór, bez routera i bez przekazywania danych).

**Zrobione:**
- Docker: redis, ai i frontend startują; frontend na http://localhost:5173 zwraca 200 i poprawnie rozwiązuje zależności. Backend jest `unhealthy` (`database: not_configured`, brak `SUPABASE_DB_URL` w `.env`), a Compose nie startuje frontendu, dopóki backend nie jest zdrowy. Sam frontend: `docker compose up -d --build --no-deps frontend`.
- Układ jak w Google Maps: wyszukiwarka ulic/adresów z podpowiedziami podczas pisania (Photon, opóźnienie 250 ms, strzałki + Enter; zapas po Enterze: Nominatim z limitem 1 zapytanie/s; tylko Kraków) -> karta miejsca z „Trasa” i „Oceny” -> panel trasy. Filtry w zwijanej karcie, legenda na dole, konto w prawym górnym rogu.
- Panel trasy: pola A i B z wyszukiwarką ulic, „Wskaż na mapie” i „Moja lokalizacja”; punkt z mapy dostaje nazwę ulicy z `GET /segments/nearest` zamiast współrzędnych; przystanki pośrednie (do 3, numerowane pinezki; `via` poza kontraktem), profil, wymagania: 5 wymiarów, każdy z grubym suwakiem na trzy kroki Nieważne/Ważne/Bardzo ważne (waga 0/2/3); „Wyznacz trasę” woła `POST /route` (ORS przez backend): lista propozycji z czasem, dystansem, oceną i pokryciem ocen, wybrana trasa niebieska na mapie, pozostałe szare; przystanki idą jako `via` (kontrakt 5.8); rank 1 = najlepsza dla wymagań (z kosztem czasu względem najszybszej), rank 2 = najszybsza; błędy punktów (404 z `details.field`) opisane po polsku (`routing/planRoute.ts`); wyniki znikają po zmianie punktów, profilu lub wymagań; podgląd zapytania zostaje.
- Mapa: kolorowe odcinki wstawione pod warstwy etykiet (nazwy ulic nie są zasłonięte), etykiety ciemne z białym obrysem, nazwy ulic pogrubione (font Noto Sans Bold; Medium nie istnieje w OpenFreeMap). Widok satelitarny: przełącznik „Mapa / Satelita”, kafelki Esri World Imagery (warunki użycia do sprawdzenia przed demo, nie cache'ować offline w PWA), w satelicie zostają tylko białe etykiety i odcinki z białym obrysem.
- Grupy odcinków (kontrakt 4): kliknięcie kawałka ulicy zaznacza na mapie całą grupę (ok. 500 m, `GET /groups/{id}`), a panel opisuje całą grupę (nazwa, długość, „od … do …”, średnie grupy, oceny grupy); „Szacunek na podstawie podobnych dróg” przy braku ocen. Bez grupy (mocki, backend niedostępny) panel pokazuje pojedynczy odcinek.
- Filtry: usunięty przełącznik „Tylko ocenione”; bez emotek w panelu filtrów oraz na przyciskach „Filtry i kolory” i „Trasa”.
- Panel trasy: usunięte „Wyczyść wszystko” i komunikat pod przyciskiem; przełącznik Mapa/Satelita przeniesiony na prawą stronę (obok zoomu), dzięki czemu panel trasy ma pełną wysokość okna i nie trzeba go przewijać do „Wyznacz trasę”.
- Zaznaczenie ulicy na mapie: nieprzezroczysty niebieski obrys z białą przerwą pod kolorową linią ocen (bez ciemnych kropek na stykach odcinków).
- Trasa nie uwzględnia parkingów: wymagania tylko dla 4 wymiarów (`ROUTE_DIMENSIONS`), waga parkingów zawsze 0 w zapytaniu i brak ich w ocenach trasy. Usunięty „Podgląd zapytania”.
- Stan w `routing/useRouteDraft.ts`, szukanie w `api/geocode.ts`.
- Własny endpoint `GET /search` (backend `app/search.py`, opis w kontrakcie 5.10, testy `test_search.py`): podpowiedzi ulic z naszej bazy, Photon tylko dla adresów/miejsc lub gdy backend nie działa. Zmiany backendu i kontraktu do wydzielenia do osobnych gałęzi/PR-ów (B1 jest właścicielem backendu).

**Dalej / blokery:**
- Piesi (`foot-walking`) nadal przez ORS lub przykładowe dane, bez własnego grafu.
- Limit 2000 odcinków na odpowiedź (kontrakt 5.2): na dużym ekranie przy zoomie ok. 13 backend zwraca 422 „Przybliż mapę”, więc kolorów nie widać, dopóki się nie przybliży. Do rozważenia: pobieranie kafelkami po stronie frontu albo wyższy limit/agregacja po stronie backendu.
- Kontrakt radzi pokazywać wyniki szacowane z grupy (`scores_source: "group"`) jaśniej na mapie: jeszcze nie zrobione.
- Esri World Imagery nie jest w MAP_STACK: dopisać (osobny PR) po sprawdzeniu warunków.
- Do pełnego Compose potrzebna konfiguracja bazy w `.env` (B1, `docs/B1_HANDOFF.md`); hasło DB wpisuje osoba z dostępem, nie w czat.
- Photon/Nominatim (adresy, miejsca) są wołane bezpośrednio z przeglądarki; Photon nie jest w MAP_STACK. Do decyzji, czy zostawić.



## 2026-10-03 — Beata — gałąź `frontend/auth-rating`

**Zadanie:** logowanie (Supabase Auth), formularz oceny i dodawanie opinii (kroki 14 planu).

**Zrobione:**
- `@supabase/supabase-js`; klient tylko do logowania (`src/lib/supabase.ts`, klucz publishable z `.env`, nigdy secret).
- `src/auth/`: `AuthProvider` (sesja), `AuthDialog` (logowanie i rejestracja, polskie błędy), `AccountButton` w nagłówku lewego panelu.
- `client.ts`: JWT w `Authorization: Bearer`, `postRating` (`POST /segments/{id}/ratings`) i `postComment` (`POST /segments/{id}/comments`), przy braku backendu mock.
- `RatingForm` (5 wymiarów 1–5, każdy opcjonalny, pora dnia) i `CommentForm` (do 1000 znaków) w panelu odcinka.

**Dalej / blokery:**
- Przetestować logowanie na prawdziwym koncie i potwierdzenie e-mail (ustawienie w Supabase Auth).
- Zdjęcia (przesyłanie, galeria) czekają na `backend/photos` (B2).
- Klucz `sb_secret_...` trafił do czatu: zrotować w Supabase.

## 2026-10-03 — Beata — gałąź `frontend/map`

**Zadanie:** mapa Krakowa z kolorowaniem odcinków wg wymiaru, filtr i panel szczegółów (kroki 12–13 planu).

**Zrobione:**
- Zależności: `maplibre-gl` 6, `react-map-gl` 8 (import z `react-map-gl/maplibre`), worker MapLibre ustawiony pod Vite.
- `src/api/types.ts` (typy z kontraktu), `client.ts` (`GET /segments`, `GET /segments/{id}`), `mocks.ts` (dane przykładowe, gdy backend nie odpowiada lub `VITE_USE_MOCKS=true`).
- `MapView`: styl Positron, `maxBounds` Krakowa, jedna warstwa `line` z `interpolate` po polu `score` wybranego wymiaru, pobieranie po `onMoveEnd` (debounce, abort, od zoomu 13), podświetlenie wybranego odcinka.
- `FilterBar` (lewy panel): wybór wymiaru lub oceny ogólnej, min. ocena, „tylko ocenione”, „bez przeszkód”, legenda. Filtry „ogólna” i „bez przeszkód” działają po stronie przeglądarki (kontrakt ich nie ma).
- `SegmentPanel` (prawy, z regulowaną szerokością): ocena główna, oceny wymiarów, dane OSM, przeszkody, podsumowanie AI (mock), opinie w stylu Google Maps (`OpinionCard`: średnia autora, rozwijana szczegółowa ocena, 👍/👎 lokalnie).
- Nazwa w UI: „Rate My Road”.

**Dalej / blokery:**
- Sprawdzić wizualnie w przeglądarce i na telefonie (nie zrobione).
- Po gotowości backendu przetestować na prawdziwym `/segments`.
- Następne gałęzie: `frontend/auth-rating`, `frontend/routing`, `frontend/pwa`.
- Typ `Opinion` (ocena autora przy komentarzu, głosy 👍/👎) jest poza kontraktem: potrzebny osobny PR do `docs/CONTRACT.md` uzgodniony z B1 i B2.
- Prawdziwe ulice dopiero po seedzie z OSM (B2, `db/seed-krakow`) i `GET /segments` (B1, `backend/core`); mocki mają zgadnięte współrzędne.
- Skill `frontend` jest na gałęzi `docs/skills` (B1), jeszcze nie w `main`.
