# Własny graf tras (B2): jak go używać

Dla backendu (`POST /route`) i AI (kalibracja kosztu). Stan: 2026-10-05, projekt `lsfpirkqdtjkcaujnsde`.
Zakres: `driving-car` i `cycling-regular`. `foot-walking` zostaje przy ORS. Kontrakt `POST /route` bez zmian.

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
- `siła` domyślnie: **8 dla auta, 3 dla roweru** (parametr `p_strength`). Auto potrzebuje więcej, bo różnice
  prędkości między klasami dróg przeważają nad ocenami przy niskiej sile. Zmierzone: auto, trasa A→B, ruch=3:
  siła 3 → bez zmiany trasy; siła 10 → odcinki na drogach głównych 7,7 km → 1,4 km, ruch 2,63 → 3,57, czas +36%.
  Rower, siła 3: ruch 3,59 → 4,67, czas +19%.
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

### Co zrobić z wynikiem w `POST /route`

- `geometry` — sklej `geom` kolejnych wierszy w jeden LineString (końce się schodzą, sprawdzone).
- `distance_m` = suma `length_m`; `duration_s` = suma `time_s`.
- `scores` — średnie ważone długością krawędzi; `score` — ważona suma wg wag użytkownika.
- `coverage` — udział długości krawędzi z `rated = true`.
- `segment_ids` — niepuste, unikalne `segment_id`.
- Dobrym wynikiem dla UI są dwie trasy: ta po wagach użytkownika oraz najszybsza (wszystkie wagi 0), żeby pokazać
  ile czasu kosztuje lepsza trasa.

## Obiekty w bazie

| Obiekt | Rola |
|---|---|
| `routing_edges` | topologia: `osm_ways` pocięte w węzłach OSM (92 393 krawędzi), kierunki auto/rower, prędkości, `segment_id` |
| `routing_nodes` | 78 496 węzłów, flagi `car_main`/`bike_main` (największa silnie spójna składowa) |
| `routing_edge_dims` (widok) | oceny krawędzi: oceny → priory OSM → 3 |
| `routing_graph` (widok mat.) | wszystko do liczenia kosztu w jednej tabeli; odświeżany z ocenami co 2 min |
| `find_route(...)` | wyszukiwanie trasy wg wag |
| `rebuild_routing()` | pełna przebudowa po ponownym imporcie OSM (topologia + `routing_graph`) |

Spójność (silna, z kierunkami): auto 96,5%, rower 96,2% długości w jednej składowej.
Mapowanie ocen: krawędź bierze oceny odcinka `segments` o tym samym `osm_way_id`, najbliższego jej środka
(32 589 krawędzi ma odcinek; reszta jedzie na priorach). Dziś ocenianych krawędzi jest 1 936 (dane demo
wokół Rynku).

## Wydajność

Free-tier Supabase: typowa trasa autem ok. 0,4 s, rower przez całe miasto ok. 1,1 s. Zapytanie szuka najpierw
w korytarzu wokół punktów, a przy braku trasy w całej sieci. Algorytm: `pgr_bddijkstra` (dokładny; dwukierunkowy
A* dał w teście inną trasę, więc nie jest używany).

## Czego graf jeszcze nie robi

- zakazy skrętu (relacje `restriction`) i bariery; kierunki ruchu są uwzględnione,
- przeszkody (`obstacles`): zamknięcie powinno wyłączać krawędź, remont dodawać karę,
- pora dnia (`segment_stats_by_time`), parkingi przy celu, trasy alternatywne,
- ruch pieszy (zostaje ORS).

## Utrzymanie

Po ponownym imporcie OSM (`scripts/load_osm_routing.py`, a po nim przebudowie grup): `select * from public.rebuild_routing();`
(chwilę trwa; zwraca liczbę krawędzi i spójność). Test spójności z kierunkami zawiera już ta funkcja;
`scripts/check_graph.py --edges routing_edges` sprawdza spójność bez kierunków.
