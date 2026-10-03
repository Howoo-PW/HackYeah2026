# Dziennik FE — frontend

Najnowsze wpisy na górze. Szablon: [README.md](README.md).

<!-- wpisy -->



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
