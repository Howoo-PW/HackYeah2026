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

1. **Żądanie:** `{ from, to, via?, profile, weights }`. `from`/`to`/`via[]` to `{lat, lon}`; `via` to do 5 punktów
   pośrednich w kolejności jazdy; `profile`: `driving-car` | `cycling-regular` | `foot-walking`; `weights`: pięć
   suwaków 0–3 (`surface`, `views`, `safety`, `traffic`, `parking`), czyli to, na czym użytkownikowi zależy
   (same zera = najszybsza trasa). Nazwy w UI: CONTRACT.md sekcja 3.
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
6. **Piesi** (`foot-walking`) są jeszcze na zewnętrznym silniku lub przykładowych danych (jedna trasa przy `via`,
   kilka bez): nie traktuj tych wyników jako docelowych, własny graf pieszy dopiero powstanie.

## Stan

- origin/frontend/map scalono: mapa, filtry i panel działają na localhost:5173.
- Build i lint PASS. Bez DB frontend korzysta z oznaczonych danych demo.
- Core B1 udostępnia kontrakt endpointów dla integracji FE.

## TODO

- frontend/auth-rating: Auth i formularze.
- frontend/routing: wybór A→B z `via`, suwaki wag, rysowanie tras i lokalizacja użytkownika według sekcji
  „Trasy: co podłączyć” (backend gotowy); frontend/pwa: manifest/service worker.
- Sprawdzić interfejs i czytelne błędy na telefonie podczas próby demo.
