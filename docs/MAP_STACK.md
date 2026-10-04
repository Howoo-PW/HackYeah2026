# Rate My Road — stos mapowy

Zweryfikowano 2026-10-03: wersje z npm i PyPI, zasady usług ze stron operatorów. Przed demo sprawdźcie limity jeszcze raz — operatorzy zmieniają je bez zapowiedzi.

Kryteria: open source, darmowe na hackathon, dobra dokumentacja, działa z React + Vite + TypeScript i Pythonem.

## 1. Decyzje w skrócie

| Warstwa | Wybór | Dlaczego |
|---|---|---|
| Silnik mapy (frontend) | **MapLibre GL JS** | Mapy wektorowe, kolorowanie linii wg danych (oceny), płynne na telefonie, licencja BSD |
| Integracja z React | **react-map-gl** (`react-map-gl/maplibre`) | Komponenty `Map`, `Source`, `Layer`, `Marker`, `Popup`; utrzymywany przez vis.gl (OpenJS Foundation) |
| Kafelki (podkład mapy) | **OpenFreeMap** | Darmowe, bez klucza API i rejestracji, kafelki wektorowe z OSM |
| Dane dróg i parkingów | **Overpass API** (jednorazowy import Krakowa) | Zapytanie po tagach w bbox, wynik w JSON |
| Zapasowo dla danych | **Geofabrik** (wycinek `malopolskie`) + **pyosmium** | Gdy Overpass jest przeciążony |
| Trasy | **Własny graf dróg w bazie** (OSM w `osm_ways`, SQL `find_route`) | Auto, rower i piesi, koszt z ocen i wag użytkownika; opis w [ROUTING_GRAPH.md](ROUTING_GRAPH.md) |
| Wyszukiwanie adresów | **Nominatim** | Tylko wyszukiwanie po zatwierdzeniu, bez podpowiedzi przy pisaniu |
| Obliczenia przestrzenne | **PostGIS** (Supabase) | Dopasowanie do odcinków, bbox, najbliższy odcinek |

**Odrzucone:**
- **Leaflet / react-leaflet** — Leaflet rysuje mapy rastrowe, kolorowanie tysięcy odcinków jest wolniejsze. `react-leaflet` ma licencję Hippocratic 2.1, która nie jest licencją open source zatwierdzoną przez OSI.
- **Kafelki `tile.openstreetmap.org`** — dopuszczalne do lekkiego użycia, ale tylko rastrowe i z zakazem cache'owania offline. OpenFreeMap jest lepszy do PWA.
- **Mapbox, Google Maps** — wymagają klucza i płatności powyżej limitu, a ich warunki ograniczają łączenie danych z innymi źródłami.
- **osmnx** — wygodny, ale ciężki (geopandas, networkx). Do jednorazowego importu wystarczy Overpass albo pyosmium.

## 2. Frontend (npm)

| Pakiet | Wersja | Licencja | Do czego |
|---|---|---|---|
| `maplibre-gl` | 6.11.2 | BSD-3-Clause | Silnik mapy |
| `react-map-gl` | 8.1.3 | MIT | Komponenty React (import z `react-map-gl/maplibre`) |
| `@supabase/supabase-js` | 2.117.2 | MIT | Logowanie (Supabase Auth) |
| `vite-plugin-pwa` | 2.0.0 | MIT | Manifest i service worker (jeszcze niepodłączony, branch `frontend/pwa`) |

Uwagi:
- **MapLibre 6 + Vite:** trzeba wskazać plik workera, inaczej mapa się nie załaduje:
  ```ts
  import { setWorkerUrl } from 'maplibre-gl';
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
  import 'maplibre-gl/dist/maplibre-gl.css';
  setWorkerUrl(workerUrl);
  ```
- **Import w MapLibre 6:** `import * as maplibregl from 'maplibre-gl'` (nie domyślny import jak w v4/v5).
- **`vite-plugin-pwa` 2.0.0** wyszedł dzisiaj. Jeśli coś nie działa, przypnijcie ostatnią wersję 1.x.
- **Kolorowanie odcinków:** jedna warstwa `line` z wyrażeniem `interpolate` na polu `scores.<wymiar>` — bez osobnych obiektów dla każdego odcinka.
- **Atrybucja:** MapLibre dodaje „© OpenStreetMap contributors” automatycznie ze stylu. Nie ukrywajcie jej.

Style OpenFreeMap (`mapStyle` w `<Map>`):
- `https://tiles.openfreemap.org/styles/liberty` — kolorowy, domyślny
- `https://tiles.openfreemap.org/styles/positron` — jasny, stonowany: **zalecany**, bo kolorowe odcinki ocen są na nim najlepiej widoczne
- `https://tiles.openfreemap.org/styles/bright`

## 3. Backend i import danych (PyPI)

| Pakiet | Wersja | Do czego |
|---|---|---|
| `psycopg` | 3.3.3 | Połączenie z Postgres/PostGIS (zapytania SQL przestrzenne, pula połączeń) |
| `httpx` | 0.28.1 | Wywołania serwisu AI i Nominatim; skrypty importu używają `urllib` (Overpass) |
| `pillow` | 11.3.0 | Zdjęcia: usuwanie EXIF i miniatury |

Wersje i pełna lista: `backend/requirements.txt`. Zdjęcia trafiają do Supabase Storage przez jego API HTTP (bez pakietu `supabase`). Pominięte: `overpy` (wystarczy `urllib`/`httpx`), `shapely`, `geoalchemy2` (geometrie liczy PostGIS).

## 4. Zewnętrzne usługi — zasady użycia

| Usługa | Limit / zasady | Co z tego wynika dla nas |
|---|---|---|
| **OpenFreeMap** | Bez klucza, bez deklarowanych limitów; utrzymywany z darowizn; MIT; atrybucja OSM wymagana | Podkład mapy. Nie pobierajcie kafelków masowo |
| **OSM tile server** | Tylko interaktywne oglądanie; zakaz pobierania obszarów offline i prefetchu; własny User-Agent; cache ≥ 7 dni; atrybucja widoczna | Nie używamy. Gdyby był potrzebny — **wyłączyć cache kafelków w service workerze PWA** |
| **Overpass API** (`overpass-api.de`) | < 10 000 zapytań i < 1 GB dziennie; bez równoległych zapytań; własny User-Agent; przy 429 czekać 30 s; serwer bywa przeciążony | Jeden import Krakowa = kilka zapytań. Wynik zapisujemy w plikach seed, aplikacja nie odpytuje Overpass na żywo |
| **Nominatim** | Max 1 zapytanie/s; **zakaz podpowiedzi przy pisaniu**; własny User-Agent; wyniki trzeba cache'ować | Wyszukiwarka adresu tylko po Enter, przez backend z cache |

Wspólne zasady:
- Każde wywołanie z backendu ma nagłówek `User-Agent: RateMyRoad/0.1 (kontakt: <email zespołu>)`.
- Klucze tylko w `.env` backendu, nigdy w frontendzie.
- Na produkcję (po hackathonie): własny serwer kafelków lub płatny dostawca.

## 5. Kolejność wdrożenia

1. Frontend: MapLibre + react-map-gl + styl Positron, mapa wycentrowana na Kraków (`[19.94, 50.06]`, zoom 13), granice przesuwania do bbox Krakowa (`maxBounds`).
2. Import: `scripts/import_osm.py` (httpx → Overpass → shapely → pliki seed).
3. Warstwa odcinków: `GET /segments?bbox=` → `Source` GeoJSON → `Layer` typu `line`, kolor wg wybranego wymiaru.
4. Trasy: własny graf w backendzie (`POST /route`), wyświetlenie jako osobna warstwa `line`.

## 6. MCP dla map

Żadna z używanych usług (MapLibre, OpenFreeMap, OSM, Overpass) nie ma oficjalnego serwera MCP. Dostępne są tylko projekty społecznościowe — nie dodajemy ich (zasada w [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md), sekcja 10).

Zamiast tego **Context7** (w `.mcp.json`): Claude pobiera aktualną dokumentację bibliotek z tej listy. W promptach dopisujcie „use context7”, np. „dodaj warstwę line w react-map-gl z kolorem wg właściwości, use context7”.

## 7. Dokumentacja

- MapLibre GL JS — https://maplibre.org/maplibre-gl-js/docs/ (przykłady: https://maplibre.org/maplibre-gl-js/docs/examples/)
- Specyfikacja stylów i wyrażeń (kolorowanie wg danych) — https://maplibre.org/maplibre-style-spec/
- react-map-gl — https://visgl.github.io/react-map-gl/
- OpenFreeMap — https://openfreemap.org/quick_start/
- Overpass QL — https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL
- Overpass Turbo (testowanie zapytań w przeglądarce) — https://overpass-turbo.eu/
- PostGIS — https://postgis.net/docs/
- pyosmium — https://docs.osmcode.org/pyosmium/latest/
- Wycinki Geofabrik (Polska → małopolskie) — https://download.geofabrik.de/europe/poland.html
- Polityka kafelków OSM — https://operations.osmfoundation.org/policies/tiles/
- Polityka Nominatim — https://operations.osmfoundation.org/policies/nominatim/
