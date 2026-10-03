# Dziennik FE — frontend

Najnowsze wpisy na górze. Szablon: [README.md](README.md).

<!-- wpisy -->

## 2026-10-03 — Beata — gałąź `frontend/map`

**Zadanie:** mapa Krakowa z kolorowaniem odcinków wg wymiaru, filtr i panel szczegółów (kroki 12–13 planu).

**Zrobione:**
- Zależności: `maplibre-gl` 6, `react-map-gl` 8 (import z `react-map-gl/maplibre`), worker MapLibre ustawiony pod Vite.
- `src/api/types.ts` (typy z kontraktu), `client.ts` (`GET /segments`, `GET /segments/{id}`), `mocks.ts` (dane przykładowe, gdy backend nie odpowiada lub `VITE_USE_MOCKS=true`).
- `MapView`: styl Positron, `maxBounds` Krakowa, jedna warstwa `line` z `interpolate` po polu `score` wybranego wymiaru, pobieranie po `onMoveEnd` (debounce, abort, od zoomu 13), podświetlenie wybranego odcinka.
- `FilterBar`: wybór wymiaru, min. ocena, „tylko ocenione”, legenda. `SegmentPanel`: oceny, dane OSM, przeszkody.

**Dalej / blokery:**
- Sprawdzić wizualnie w przeglądarce i na telefonie (nie zrobione).
- Po gotowości backendu przetestować na prawdziwym `/segments`.
- Następne gałęzie: `frontend/auth-rating`, `frontend/routing`, `frontend/pwa`.
- Skill `frontend` jest na gałęzi `docs/skills` (B1), jeszcze nie w `main`.

