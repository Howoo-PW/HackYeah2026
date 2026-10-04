# Własny graf tras (B2): jak go używać

Dla backendu (`POST /route`) i AI (kalibracja kosztu). Stan: 2026-10-05, projekt `lsfpirkqdtjkcaujnsde`.
Zakres: `driving-car`, `cycling-regular` i `foot-walking` (piesi po drogach, nie po chodnikach). Zewnętrznego
silnika tras (ORS) już nie używamy.

## Idea

Użytkownik zaznacza, co go obchodzi (wagi 0–3 dla `surface`, `views`, `safety`, `traffic`, `parking`, czyli
dokładnie wymiary, które oceniają użytkownicy). Z tych wag baza liczy koszt **każdej krawędzi przy każdym
zapytaniu** i znajduje najtańszą ścieżkę. Oceny nie są wpisane na stałe w graf, więc nowa ocena zmienia trasy
po najbliższym odświeżeniu (co 2 minuty), bez przebudowy.

```
koszt krawędzi = czas przejazdu * mnożnik
mnożnik        = 1 + siła * (max(w) / 3) * suma(w_d * kara_d) / suma(w_d)
kara_d         = (5 - ocena_d) / 4        (ocena 5 → 0, ocena 1 → 1)
```

- Wszystkie wagi 0 → mnożnik 1 → najszybsza trasa.
- Jeden wymiar na 3 → najgorsze drogi kosztują do (1 + siła) razy więcej niż ich czas.
- `siła` domyślnie: **8 dla auta, 3 dla roweru i pieszych** (parametr `p_strength`). Auto potrzebuje więcej, bo różnice
  prędkości między klasami dróg przeważają nad ocenami przy niskiej sile. Zmierzone: auto, trasa A→B, ruch=3:
  siła 3 → bez zmiany trasy; siła 10 → odcinki na drogach głównych 7,7 km → 1,4 km, ruch 2,63 → 3,57, czas +36%.
  Rower, siła 3: ruch 3,59 → 4,67, czas +19%. Piesi, siła 3: ruch 3,33 → 3,99, czas +17% (inna para punktów:
  3,32 → 4,82, +24%); siła 8 dawała +68% czasu, więc dla pieszych zostaje 3.
- Ocena krawędzi: `segment_scores` (własne oceny → grupa → średnia typu drogi); bez niej priory z OSM
  (`surface`/`smoothness` → nawierzchnia, `lit` → bezpieczeństwo, klasa drogi → ruch), inaczej 3.
  `views` i `parking` bez ocen = 3 (neutralnie).

## Wywołanie

```sql
select * from public.find_route(
  'cycling-regular',            -- 'driving-car' | 'cycling-regular'
  19.9373, 50.0617,             -- skąd: lon, lat
  19.9700, 50.0360,             -- dokąd: lon, lat
  p_w_surface := 2, p_w_views := 3, p_w_safety := 0, p_w_traffic := 1, p_w_parking := 0
);
```

Zwraca jeden wiersz na krawędź, w kolejności jazdy: `seq`, `edge_id`, `way_id`, `segment_id`, `forward`,
`length_m`, `time_s`, oceny krawędzi `surface/views/safety/traffic/parking`, `rated` (czy krawędź ma oceny
użytkowników) i `geom` (LineString zwrócony zgodnie z kierunkiem jazdy). Pusty wynik = brak trasy
(punkt poza siecią albo ten sam węzeł). Nieznany profil → błąd `22023`. Funkcja jest dostępna tylko dla roli
`postgres`/`service_role` (backend), nie przez publiczne API.

Punkty początku i końca są przyciągane do najbliższego węzła w największej silnie spójnej składowej sieci
danego profilu (nie utkniesz na parkingu odciętym od reszty).

### `POST /route` w backendzie (zrobione: `backend/app/routing/graph.py`)

Wszystkie trzy profile (`driving-car`, `cycling-regular`, `foot-walking`) idą z grafu i zachowują się tak samo.

- **Trasy w odpowiedzi.** Bez wag: jedna trasa, najszybsza. Z wagami: **rank 1 = najlepsza trasa dla priorytetów
  użytkownika**, **rank 2 = najszybsza** (pomijana, gdy to ta sama trasa), żeby UI pokazało, ile czasu kosztuje lepsza
  trasa. Rank nie wynika z `score` (ten liczą tylko oceny, a koszt grafu także priory OSM), tylko z definicji.
- `geometry` — geometrie krawędzi sklejone w jeden LineString (punkt wspólny dwóch krawędzi tylko raz). Linia zaczyna
  się w węźle sieci najbliższym punktowi `from` (nie w nim samym) i kończy w węźle najbliższym `to`; marker
  użytkownika rysuje frontend.
- `distance_m` = suma długości krawędzi, `duration_s` = suma czasów (prędkości z OSM, bez korków).
- `scores` — średnie ważone długością z **własnych ocen odcinków** (`segment_scores`, w tym szacunek z grupy);
  wymiar, którego nikt nie ocenił na trasie, ma `null`. Priory z OSM (używane tylko do wyboru trasy) nie trafiają do
  `scores`: nie udajemy ocen, których nikt nie wystawił.
- `score` — średnia z wymiarów wybranych przez użytkownika, ważona jego wagami; ta sama reguła dla obu tras, więc
  są porównywalne. Bez ocen na trasie `null`.
- `coverage` — udział długości trasy na odcinkach, które mają wynik.
- `segment_ids` — wszystkie odcinki, przez które biegnie trasa (także nieocenione: frontend może zachęcić do oceny).
- Krawędź jest dopasowana do **jednego** odcinka (najbliższego jej środka), więc na długiej krawędzi obejmującej kilka
  odcinków liczy się wynik jednego z nich.

**Żądanie** (`via` i `time_of_day` są opcjonalne; kontrakt: `docs/CONTRACT.md`, sekcja 5.8):

```json
{ "from": {"lat": 50.0668, "lon": 19.9341}, "to": {"lat": 50.0670, "lon": 19.9302},
  "via": [{"lat": 50.0654, "lon": 19.9307}],
  "profile": "driving-car",
  "weights": {"surface": 2, "views": 0, "safety": 0, "traffic": 0, "parking": 0},
  "time_of_day": "evening" }
```

- `time_of_day`: `morning` | `day` | `evening` | `night`. Brak = aktualna pora dnia w Warszawie (ta sama reguła co przy
  nowych ocenach). Patrz sekcja „Pora dnia”.

- `via`: do 5 punktów pośrednich, trasa przechodzi przez nie w podanej kolejności (start → via[0] → … → koniec).
  Każdy odcinek między dwoma przystankami szuka się osobno, a wyniki skleja w jedną trasę. Przystanek, który wypada w tym
  samym węźle co poprzedni, nie dodaje odcinka. Odpowiedź ma ten sam kształt co bez `via` (jedna linia, sumy
  dystansu i czasu), więc frontend nie musi niczego zmieniać po swojej stronie.
- Błąd punktu pośredniego wskazuje jego indeks: `details.field = "via[0]"`.
- Czas: każdy przystanek dodaje jedno wyszukiwanie na wariant (do ok. 1 s w najgorszym przypadku na darmowej bazie).

Błędy: punkt dalej niż 600 m od sieci drogowej danego profilu → `404 NOT_FOUND` z `details.field` (`from`/`via[i]`/`to`);
brak trasy (np. ten sam punkt) → `404`; punkt poza obsługiwanym obszarem → `422 OUT_OF_AREA`; wagi poza 0–3 → `422`;
limit 30 żądań na minutę na IP (kontrakt, sekcja 9) → `429 RATE_LIMITED`. Za reverse proxy wszystkie żądania mają
wtedy ten sam adres IP, więc przed produkcją trzeba skonfigurować prawdziwy adres klienta.
Limit 600 m (`MAX_SNAP_M` w `routing/graph.py`) jest celowo luźny: strefy piesze w centrum leżą kilkaset metrów od
najbliższej drogi dla auta.

**Obszar działania jest w jednym miejscu**: granice obsługiwanego obszaru to stała `KRAKOW` w `backend/app/geo.py` (`routing/geo.py` tylko ją importuje)
(sprawdzanie `OUT_OF_AREA`); nic innego w module tras nie zakłada konkretnego miasta. Dodając kolejne miasto, trzeba
tam rozszerzyć obszar, załadować sieć OSM nowego obszaru (`scripts/load_osm_routing.py`) i przebudować graf
(`select * from rebuild_routing();`).

Health: `checks.routing` jest `ok`, gdy graf jest zbudowany dla wszystkich trzech profili (w `routing_graph` są
krawędzie auta, roweru i pieszych); `not_configured` bez bazy; `error`, gdy grafu (któregoś profilu) nie ma.

## Piesi

Pieszy chodzi **po sieci dróg**, a nie po chodnikach (decyzja zespołu): chodniki i przejścia nie są modelowane, bo
ulica, do której należą, ich zastępuje. Reguły w `scripts/osm_access.py` (`foot_direction`):

- dostępne: wszystkie zwykłe drogi (`primary`…`residential`, `living_street`, `service`), ulice piesze (`pedestrian`),
  ścieżki (`path`), drogi gruntowe (`track`), `footway` (np. wspólne ścieżki dla pieszych i rowerów);
- tylko z `foot=yes|designated|permissive`: `cycleway`, `trunk`; nigdy: autostrady i drogi ekspresowe;
- wyłączone: `foot=no`, dostęp prywatny/dla klientów, obszary (`area=yes`), `footway=sidewalk`, `footway=crossing`,
  parkingowe i dojazdowe drogi serwisowe, schody;
- **kierunek zawsze w obie strony** (jednokierunkowość i rondo nie wiążą pieszego, chyba że `oneway:foot`);
- prędkość 5 km/h (jedna stała).

Dane: wszystkie 58 531 dróg z `osm_ways` ma `foot_dir`; dostępnych dla pieszych jest 55 386. 161 ulic pieszych
(12,5 km), których auto i rower nie używały, dociągnął `scripts/load_osm_foot.py` (reszta `highway=pedestrian` miała
`area=yes` albo zakaz). Spójność: 96,0% długości w jednej silnie spójnej składowej. Stare Miasto jest osiągalne:
Rynek leży 15 m od sieci pieszej (dla auta 511 m), a trasa Rynek → Wawel to 1,47 km, 18 min, ulicą Grodzką.

Ograniczenia: piesi mogą dostać trasę wzdłuż ruchliwej drogi bez chodnika (łagodzą to wagi „ruch” i „bezpieczeństwo”
oraz priory z klasy drogi); nie ma ścieżek w parkach ani skrótów między blokami (samodzielne `footway`: faza 2,
gdyby była potrzebna), schodów, przejść ze światłami jako kosztu ani obszarów pieszych (`area=yes`).

## Obiekty w bazie

| Obiekt | Rola |
|---|---|
| `routing_edges` | topologia: `osm_ways` pocięte w węzłach OSM (92 693 krawędzi), kierunki auto/rower/piesi, prędkości, `segment_id` |
| `routing_nodes` | 78 737 węzłów, flagi `car_main`/`bike_main`/`foot_main` (największa silnie spójna składowa) |
| `routing_edge_dims` (widok) | oceny krawędzi: oceny → priory OSM → 3 |
| `routing_graph` (widok mat.) | wszystko do liczenia kosztu w jednej tabeli; odświeżany z ocenami co 2 min |
| `routing_edge_obstacles` (widok) | aktywne przeszkody przypisane do najbliższej krawędzi (osobno auto, rower, piesi), liczone na żywo |
| `blend_score(...)`, `segment_scores_for_time(pora)` | ocena odcinka dla pory dnia: oceny z tej pory zmieszane z ocenami ogólnymi |
| `find_route(...)` | wyszukiwanie trasy wg wag, przeszkód i pory dnia |
| `routing_snap(profil, lon, lat)` | najbliższy węzeł sieci i odległość do niego (backend odrzuca punkty > 600 m od drogi) |
| `rebuild_routing()` | pełna przebudowa po ponownym imporcie OSM (topologia + `routing_graph`) |

Spójność (silna, z kierunkami): auto 96,5%, rower 96,2%, piesi 96,0% długości w jednej składowej.
Mapowanie ocen: krawędź bierze oceny odcinka `segments` o tym samym `osm_way_id`, najbliższego jej środka
(32 589 krawędzi ma odcinek; reszta jedzie na priorach). Dziś ocenianych krawędzi jest 1 936 (dane demo
wokół Rynku).

## Przeszkody na trasie

Zgłoszone przeszkody (`obstacles`, endpointy w `backend/app/obstacles.py`) wpływają na trasy od razu, bez
odświeżania i bez przebudowy grafu: widok `routing_edge_obstacles` jest liczony przy każdym wyszukiwaniu.

- Aktywna przeszkoda (`valid_until` puste lub w przyszłości) trafia do **najbliższej krawędzi** dostępnej dla danego
  profilu (osobno auto, rower i piesi), nie dalej niż 50 m.
- `closure` (zamknięcie): krawędź jest niedostępna w obu kierunkach. `accident` ×3 czasu, `roadwork` ×2,
  `pothole` ×1,25, `other` ×1,2. Kilka przeszkód na jednej krawędzi: zamknięcie wygrywa, inaczej największy mnożnik.
- Mnożnik wydłuża też `duration_s`, więc czas trasy zawiera opóźnienie z przeszkody. Dotyczy także trasy „najszybszej”
  (rank 2), bo opóźnienia są prawdziwe.
- Przeszkoda leży na jednej krawędzi, więc na długiej krawędzi (do kilkuset metrów) obejmuje całą krawędź.
- Gdy zamknięcie odcina cel całkowicie, wynik to `404 NOT_FOUND` („No route found”).
- Odpowiedź `POST /route` nie zawiera listy przeszkód na trasie (kontrakt nie ma pola): trasa po prostu je omija lub
  uwzględnia opóźnienie. Do pokazania przeszkód przy trasie frontend używa `GET /obstacles`.

Endpointy: `GET /obstacles?bbox=` (publiczny, tylko aktywne, do 1000), `POST /obstacles` (zalogowany, 10/h, punkt w
obsługiwanym obszarze, `valid_until` w przyszłości lub brak; `segment_id` to najbliższy odcinek w 50 m, może być
`null`), `DELETE /admin/obstacles/{id}` (admin, 204).

## Pora dnia

Oceny mają porę dnia (`morning` 6–10, `day` 10–16, `evening` 16–22, `night` 22–6, czas warszawski). Trasa liczona dla
pory dnia używa ocen odcinków z tej pory, a nie tylko średniej z całego dnia:

```
ocena dla pory = (n * średnia_pory + K * ocena_ogólna) / (n + K)      n = liczba ocen w tej porze, K = 3
```

- Jedna nocna ocena nie przesądza o dobrze znanym odcinku (mieszanie z oceną ogólną), a odcinek, którego nikt nie
  ocenił w tej porze (albo nikt nie ocenił danego wymiaru), zachowuje ocenę ogólną.
- Dotyczy to zarówno kosztu trasy w `find_route(..., p_time_of_day => '...')`, jak i ocen raportowanych w odpowiedzi
  (`scores`, `score`): backend czyta je z `segment_scores_for_time(pora)`, więc użytkownik widzi to, według czego trasa
  została wybrana.
- Liczba ocen `n` to wszystkie oceny odcinka w danej porze (widok `segment_stats_by_time` nie rozbija ich na wymiary),
  więc przy rzadko ocenianym wymiarze waga pory bywa lekko zawyżona.
- Przeszkody nie zależą od pory dnia.

## Wydajność

Free-tier Supabase: typowa trasa autem ok. 0,4 s, rower przez całe miasto ok. 1,1 s. Zapytanie szuka najpierw
w korytarzu wokół punktów, a przy braku trasy w całej sieci. Algorytm: `pgr_bddijkstra` (dokładny; dwukierunkowy
A* dał w teście inną trasę, więc nie jest używany).

## Testy

`backend/tests/test_graph_routing.py` (offline, atrapy bazy): sklejanie geometrii, średnie ważone, coverage, ranking,
błędy, limit żądań, mapowanie wierszy z bazy. `backend/tests/test_graph_db.py` (opcjonalnie, prawdziwa baza, tylko
odczyty): `RUN_DB_TESTS=1 python -m pytest -c backend/pytest.ini backend/tests/test_graph_db.py`.
Przeszkody: `test_obstacles.py` (offline) i `test_obstacles_db.py` (prawdziwa baza, objazd wokół zamknięcia dla auta,
roweru i pieszych, wygasanie). Pora dnia: `test_time_of_day_db.py` (mieszanie ocen, trasy dla każdej pory, nocne oceny
zmieniają tylko trasę nocną). Testy zapisujące do bazy działają w transakcji wycofywanej na końcu, więc nic w niej
nie zostaje (są wolne: kilkadziesiąt sekund).

## Czego graf jeszcze nie robi

- zakazy skrętu (relacje `restriction`) i bariery; kierunki ruchu są uwzględnione,
- przeszkody (`obstacles`): zamknięcie powinno wyłączać krawędź, remont dodawać karę,
- parkingi przy celu, trasy alternatywne,
- sieć dla pieszych poza drogami: chodniki, przejścia, schody, ścieżki w parkach.

## Utrzymanie

Po ponownym imporcie OSM (`scripts/load_osm_routing.py`, a po nim przebudowie grup): `select * from public.rebuild_routing();`
(chwilę trwa; zwraca liczbę krawędzi i spójność). Test spójności z kierunkami zawiera już ta funkcja;
`scripts/check_graph.py --edges routing_edges` sprawdza spójność bez kierunków.
Pełne przeładowanie sieci (`load_osm_routing.py`) zapisuje już też kolumny pieszych. Samo uzupełnienie pieszych w
istniejącej bazie (bez ponownego pobierania dróg): `python scripts/load_osm_foot.py`, a potem `rebuild_routing()`.
Migrację można zastosować poleceniem `python scripts/apply_migration.py supabase/migrations/<plik>.sql` (jedna
transakcja, wszystko albo nic). `rebuild_routing()` konkuruje o blokady z cyklicznym odświeżaniem widoków (`pg_cron`
co 2 min); przy zakleszczeniu transakcja się wycofuje i wystarczy powtórzyć.
