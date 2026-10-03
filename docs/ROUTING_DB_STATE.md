# Baza pod własny router: stan i ustalenia

Dla B2 (graf) i AI (funkcja kosztu). Dopełnia propozycję własnego routera po ocenach (pgRouting).
Stan bazy: 2026-10-04, projekt `lsfpirkqdtjkcaujnsde`. Zakres: **`driving-car` i `cycling-regular`**.
Dla `foot-walking` `POST /route` zostaje przy ORS (jest w `backend/routing`), kontrakt się nie zmienia.

## Co jest już w bazie

| Element | Opis |
|---|---|
| `pgrouting` 3.4.1 | zainstalowany w schemacie `extensions` |
| **`osm_ways`** | **sieć dróg dla auta i roweru z OSM**: 58 370 dróg, kierunki per profil, prędkości, węzły OSM, surowe tagi (patrz niżej) |
| `segment_groups`, `segments.group_id` | 10 303 grup po ok. 500 m (kolejne kawałki jednej ulicy), każdy odcinek ma grupę |
| `segment_scores` (widok materializowany) | **wynik efektywny** odcinka w SQL: 5 wymiarów, `ratings_count`, `source` (`own`/`group`), `confidence`. Tylko odcinki z wynikiem (1 468 z 22 664). Odświeżany co 2 min |
| `effective_score(...)` | ta sama reguła co `backend/app/grouping.py` (zgodność sprawdzona na wszystkich odcinkach) |

### `osm_ways`: sieć dla auta i roweru

Załadowana skryptem `scripts/load_osm_routing.py` (Overpass, 8 kafelków, cache w `data/osm_cache/`,
ponowne uruchomienie nic nie kosztuje). Interpretacja tagów: `backend/app/osm_access.py` (testy w
`backend/tests/test_osm_access.py`). Ten sam obszar co `segments`.

| | Auto | Rower |
|---|---|---|
| Drogi | 34 418 (3 837 km) | 57 339 (5 821 km) |
| Kierunki | 25 273 dwukierunkowych, 9 145 jednokierunkowych | 49 601 dwukierunkowych, 7 738 jednokierunkowych |

Kolumny: `car_dir`, `bike_dir` (`both`/`forward`/`backward`/`none`; `forward` = zgodnie z kolejnością punktów `geom`),
`car_speed_kmh`, `bike_speed_kmh`, `maxspeed`, `surface`, `smoothness`, `lit`, `bridge`, `tunnel`, `layer`,
`junction`, `oneway`, `node_ids` (id węzła OSM każdego punktu `geom`, ta sama kolejność), `length_m`, `tags` (wszystkie surowe tagi).

Reguły (skrót): najbardziej szczegółowy tag dostępu wygrywa (`motorcar` > `motor_vehicle` > `vehicle` > `access`);
`oneway`, rondo i autostrada są domyślnie jednokierunkowe; rower może jechać pod prąd przy `oneway:bicycle=no`
albo `cycleway*=opposite*`; `footway`/`pedestrian`/`trunk` tylko z jawnym `bicycle=yes|designated|permissive`,
`motorway` nigdy; pominięte `service=parking_aisle|driveway|emergency_access|drive-through`.
`oneway=reversible|alternating` traktowane jako niedostępne. Zakazy skrętu (relacje `restriction`) i bariery
(szlabany, słupki) nie są uwzględnione, ale tagi surowe są w `tags`.

**Powiązanie z odcinkami:** `segments.osm_way_id = osm_ways.way_id` (22 275 z 22 664 odcinków ma dopasowanie;
389 bez, głównie drogi, które nowy filtr dostępu odrzuca albo zmienione w OSM od pierwszego importu).
`segments` zostaje bez zmian: id odcinków są w ocenach, grupach i `segment_scores`.

### Spójność sieci (węzły OSM, kierunki pominięte)

`python scripts/check_graph.py --osm-ways car|bike`

| Profil | Składowe | Największa |
|---|---|---|
| auto | 778 | **97,3%** długości (3 733 km) |
| rower | 1 949 | **96,4%** długości (5 613 km) |

Dla porównania graf zbudowany z końców `segments` miał tylko 74% w największej składowej: odcinki
nie mają węzłów skrzyżowań (4 112 skrzyżowań T bez wspólnego węzła). `osm_ways` ma id węzłów OSM, więc
cięcie na skrzyżowaniach jest dokładne. Tryb nie uwzględnia kierunków: to górna granica dla routera ze
skierowanym grafem, więc po zbudowaniu krawędzi trzeba sprawdzić też silną spójność.

## Zalecenia

1. **Graf buduj z `osm_ways`, nie z `segments`.** Utnij każdą drogę w węzłach OSM, które występują w co
   najmniej dwóch drogach (albo na jej końcach): `unnest(node_ids) with ordinality`, punkt = `ST_PointN(geom, n)`.
   Krawędź dostaje `way_id`, kierunki, prędkości i długość.
2. **Mapowanie na oceny:** krawędź należy do drogi `way_id`; odcinki `segments` z tym `osm_way_id` niosą oceny
   (`segment_scores`). Fragment drogi bez dokładnego odcinka bierze wynik najbliższego odcinka tej samej drogi
   (np. przez `ST_LineLocatePoint` na odcinkach o tym `osm_way_id`).
3. **Kierunki:** krawędź `forward`/`backward` według `car_dir`/`bike_dir`; koszt odwrotny nieskończony.
4. **Test spójności po zbudowaniu:** `python scripts/check_graph.py --edges routing_edges` (kolumny `source`/`target`).
   Cel: jedna dominująca składowa (ok. 96% lub więcej).
5. **Koszt krawędzi** (AI): czas = długość / prędkość profilu, razy mnożnik z `segment_scores` przez odcinek krawędzi;
   bez wiersza w `segment_scores` wartość domyślna (neutralna lub z `surface`/`smoothness`/`lit` z `osm_ways`).

## Uwagi operacyjne

- Odświeżenie danych OSM: `python scripts/load_osm_routing.py` (kasuje cache: usuń `data/osm_cache/`). Tabela jest
  zastępowana w jednej transakcji. Po odświeżeniu przebuduj graf.
- Po ponownym imporcie OSM do `segments` id odcinków się przesuwają: przebuduj grupy
  (`scripts/build_segment_groups.py`) i `refresh materialized view public.segment_scores`.
- `refresh_segment_stats()` odświeża także `segment_scores` (nadal tylko `service_role`).
- `osm_ways` jest niedostępna przez publiczne API (RLS bez polityk): backend i B2 używają roli `postgres`.
- Doradca bezpieczeństwa Supabase zgłasza `segment_scores` tak samo jak `segment_stats`: widok jest czytelny
  publicznie. To zagregowane oceny bez danych osobowych.
