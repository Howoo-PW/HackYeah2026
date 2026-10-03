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

## Stan

- Na tym branchu szkielet Vite. origin/frontend/map ma mapę, filtry i panel.
- Core B1 udostępnia kontrakt endpointów dla integracji FE.

## TODO

- frontend/map: scalić mapę; frontend/auth-rating: Auth i formularze.
- frontend/routing: trasy i wagi; frontend/pwa: manifest/service worker/lokalizacja.
- Sprawdzić interfejs i czytelne błędy na telefonie podczas próby demo.
