---
name: frontend
description: Mapa, interfejs mobilny, Supabase Auth i PWA. Właściciel FE.
---

# Frontend

Najpierw project-overview, docs/CONTRACT.md, docs/MAP_STACK.md.
React/Vite/TypeScript/Tailwind, MapLibre + react-map-gl, kafelki OpenFreeMap.
Mobile-first, geolokalizacja i PWA. Atrybucja OpenStreetMap musi być widoczna.
Supabase wyłącznie Auth, dane przez backend /api/v1. Bearer access_token do
zapisów; service_role i DB hasło nigdy w VITE_*. Typy snake_case z kontraktu.
GeoJSON [lon,lat], bbox minLon,minLat,maxLon,maxLat. traffic=5 oznacza mały ruch.
null to brak ocen; nie udawaj zerowych ocen. Błędy w error.code/message/details.
Po zapisie odśwież szczegóły i mapę; druga ocena dziś zwraca 200 zamiast 201.
Stronicowanie komentarzy 20, maksymalnie 100. Ukryte treści nie trafiają do listy.

Po zmianach: JSDoc publicznych funkcji, struktura, Stan/TODO tutaj i overview,
docs/journal/FE.md. Kontrakt zmieniaj w osobnym PR.

## Trasy: co podłączyć (backend gotowy, wysyła B2)

Backend ma gotowy `POST {VITE_API_URL}/route` (publiczny, bez tokenu). Pełny opis pól, błędów i działania:
**docs/ROUTING_GRAPH.md**, kontrakt: CONTRACT.md sekcja 5.8. Do podłączenia po stronie frontendu:

1. **Żądanie:** `{ from, to, via?, profile, weights, time_of_day? }`. `from`/`to`/`via[]` to `{lat, lon}`; `via` to do 5
   punktów pośrednich w kolejności jazdy; `profile`: `driving-car` | `cycling-regular` | `foot-walking`; `weights`:
   pięć suwaków 0–3 (`surface`, `views`, `safety`, `traffic`, `parking`), czyli to, na czym użytkownikowi zależy
   (same zera = najszybsza trasa). Nazwy w UI: CONTRACT.md sekcja 3. `time_of_day`: `morning` | `day` | `evening` |
   `night`; bez niego backend bierze aktualną porę dnia w Warszawie. Trasa i pokazane oceny liczą wtedy oceny z tej
   pory (np. „wieczorem”), więc możesz dodać wybór pory („teraz” = nie wysyłaj pola).
2. **Odpowiedź:** `routes[]`. Dla auta i roweru: `rank 1` = najlepsza trasa dla wybranych priorytetów, `rank 2`
   (opcjonalna) = najszybsza. Pokaż obie jako porównanie (ile minut i metrów kosztuje lepsza trasa). Geometria to
   GeoJSON `[lon, lat]` (od węzła przy punkcie startu do węzła przy celu, marker użytkownika rysuj sam). `score`
   i wartości w `scores` mogą być `null` (brak ocen, nie zero). `coverage` (0–1) pokaż użytkownikowi: niski =
   trasa głównie na odcinkach bez ocen. `segment_ids` to odcinki na trasie (można zachęcić do oceny).
3. **Lokalizacja użytkownika:** `navigator.geolocation` wywołuj dopiero po akcji użytkownika (przycisk „moja
   lokalizacja”) i podstaw jako `from`. Nie zapisuj pozycji i nie wysyłaj jej nigdzie poza `/route`. Działa tylko
   przez HTTPS lub localhost; obsłuż odmowę zgody i brak GPS.
4. **Błędy** (`error.code`, `error.details.field`): `404 NOT_FOUND` z `field` = `from` / `via[i]` / `to` → ten
   punkt jest za daleko od drogi dla wybranego profilu (zaznacz go na mapie); `404` bez `field` → brak trasy;
   `422 OUT_OF_AREA` → punkt poza obsługiwanym obszarem; `422 VALIDATION_ERROR`; `429 RATE_LIMITED` (30
   żądań/min na IP) → poproś o chwilę cierpliwości.
5. **Wydajność:** odpowiedź to zwykle 0,5–2 s. Przy ruszaniu suwakami używaj debounce i anuluj poprzednie
   żądanie (`AbortController`), pokazuj stan ładowania.
6. **Piesi** (`foot-walking`) działają tak samo jak auto i rower: ten sam graf, `rank 1` wg wag i opcjonalny `rank 2`
   najszybszy, `via` też. Pieszy chodzi po drogach (nie po chodnikach), w obie strony, 5 km/h.

## Przeszkody: co podłączyć (backend gotowy, wysyła B2)

Endpointy (CONTRACT.md 5.5, 5.9; wpływ na trasy: docs/ROUTING_GRAPH.md, sekcja „Przeszkody na trasie”):

1. `GET /obstacles?bbox=minLon,minLat,maxLon,maxLat` (publiczny): `{ items: Obstacle[] }`, tylko aktywne (do 1000).
   Pokaż jako markery na mapie z ikoną wg `type` (`roadwork`, `closure`, `pothole`, `accident`, `other`);
   `valid_until: null` oznacza „do odwołania”.
2. `POST /obstacles` (Bearer token): `{ type, description?, location: {lat, lon}, valid_until? }`; `description` ≤ 500
   znaków, `valid_until` ISO 8601 w przyszłości albo brak. Odpowiedź `201` z `Obstacle` (backend sam dobiera
   `segment_id` z najbliższego odcinka w 50 m, może być `null`). Błędy: `401`, `422` (`OUT_OF_AREA` lub
   `VALIDATION_ERROR`), `429` (10 zgłoszeń na godzinę). `reported_by` ustawia backend, nie wysyłaj go.
3. `DELETE /admin/obstacles/{id}` tylko dla admina (`204`).
4. Po zgłoszeniu odśwież listę przeszkód i trasę: zamknięcie (`closure`) od razu blokuje drogę w wyznaczaniu tras
   (auto, rower, piesi), a remont, wypadek, dziura i „inne” wydłużają czas przejazdu. Odpowiedź `POST /route` nie
   zawiera listy przeszkód na trasie (kontrakt jej nie ma), więc do pokazania przeszkód przy trasie użyj
   `GET /obstacles` dla jej obszaru.

## Asystent AI

Przycisk „Asystent AI” (lewy panel) otwiera `AssistantPanel`: opis słowami → `POST /assistant` (docs/ASSISTANT.md). Trasa trafia do planera przez
`route.load` + `plan.adopt` (odpowiedź asystenta jako notatka w `RoutePanel`), miejsce na kartę miejsca, ulice jako numerowane pinezki (`pins` w `MapView`)
i podświetlenie odcinków. Odpowiedź ma kilka sekund opóźnienia: pokazuj stan ładowania; błędy 429/502 mają polskie komunikaty.

## Stan

- origin/frontend/map scalono: mapa, filtry i panel działają na localhost:5173.
- Build i lint PASS. Bez DB frontend korzysta z oznaczonych danych demo.
- Core B1 udostępnia kontrakt endpointów dla integracji FE.

## TODO

- frontend/auth-rating: Auth i formularze.
- frontend/routing: wybór A→B z `via`, suwaki wag, rysowanie tras i lokalizacja użytkownika według sekcji
  „Trasy: co podłączyć” (backend gotowy); frontend/pwa: manifest/service worker.
- Sprawdzić interfejs i czytelne błędy na telefonie podczas próby demo.
