# Backend — Rate Your Ride

FastAPI. Właściciele: B1 (core), B2 (baza), AI (routing, integracja AI). Kontrakt: [../docs/CONTRACT.md](../docs/CONTRACT.md).

## Moduł `app/routing` — `POST /api/v1/route`

Trasy alternatywne z dostawcy, ocena każdej wg ocen odcinków i wag użytkownika, ranking.

| Plik | Rola |
|---|---|
| `providers.py` | `OrsProvider` (OpenRouteService, do 3 alternatyw) i `MockProvider` (bez klucza: trasa prosta + objazdy ±0,003° lon) |
| `segments.py` | `SegmentSource`: odcinki leżące na trasie. Teraz `InMemorySegmentSource` z `data/sample_segments.geojson` (dane przykładowe!). **B2 podmienia na PostGIS** — ten sam interfejs `matches(route, buffer_m, min_share)` |
| `scoring.py` | Średnie ważone długością odcinków, wynik wg wag, ranking |
| `router.py` | Endpoint, walidacja obszaru Krakowa (`OUT_OF_AREA`) |

Zasady: odcinek należy do trasy, gdy ≥ 50% jego długości leży w buforze 15 m od trasy. Bez wag wygrywa najszybsza trasa. Wymiar bez ocen = `null`, nie 0. `coverage` mówi, jaka część trasy ma oceny.

Konfiguracja: `ROUTING_PROVIDER=mock|ors`, `ORS_API_KEY`. Zdrowie: `routing` w `/api/v1/health` (bez zapytania do ORS, żeby nie zużywać limitu).

## Testy

```bash
docker compose run --rm --no-deps -v ./backend:/app backend sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```
