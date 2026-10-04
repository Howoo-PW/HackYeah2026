---
name: project-overview
description: Architektura, zasady współpracy i globalny stan projektu Rate My Road. Czytaj przed każdą pracą.
---

# Rate My Road — overview

Cel: oceny odcinków dróg Krakowa w pięciu wymiarach, mapa mobilna, komentarze,
zdjęcia, AI i ranking tras. Każda ocena ma skalę 1–5; 5 zawsze oznacza najlepiej.
Obszar: bbox `19.792,49.967,20.217,50.126`, GeoJSON `[lon,lat]`.

## Najpierw

1. Przeczytaj CLAUDE.md, docs/CONTRACT.md i IMPLEMENTATION_PLAN.md.
2. Sprawdź git status, git fetch i aktualny branch. Pracuj poza main.
3. Ustal rolę z .claude/role.local.json albo bieżącego polecenia; nie pytaj ponownie,
   gdy użytkownik podał rolę i zadanie. Zapisuj tylko dziennik tej roli.
4. Czytaj skill obszaru przed zmianami. Commit/push na prośbę użytkownika, main przez PR.

## Architektura i właściciele

- frontend: React/Vite/TypeScript/Tailwind, PWA; Supabase tylko do Auth — FE.
- backend: FastAPI; /api/v1; synchroniczna pula psycopg; publiczne odczyty,
  zapisy po JWT; PostgreSQL online i Storage — B1 core, B2 dodatki, AI trasy/cache.
- ai: osobny FastAPI, X-Internal-Key, bez dostępu do bazy — AI.
- Supabase ref lsfpirkqdtjkcaujnsde: PostGIS w extensions; schemat i migracje — B2.
- Compose: frontend 5173, backend 8000, ai 8001; bez lokalnej bazy.

Skille: backend, database, ai, frontend w sąsiednich katalogach.
Kontrakt zmieniaj wyłącznie w osobnym PR. Sekrety tylko w ignorowanym .env;
service_role i hasło DB wyłącznie w backendzie. Role wyłącznie z app_metadata.

## Automatyczna dokumentacja

Po zmianie dodaj docstringi/JSDoc do publicznych funkcji. Zaktualizuj strukturę,
Stan i TODO skilla obszaru oraz tego overview; dopisz wynik i blokery w dzienniku.
Stan opisuje bieżący branch; nie oznaczaj cudzych zmian jako scalonych.

## Stan

- 2026-10-03, backend/b1-howoo: pobrano wszystkie zdalne branche; kontrakt zatwierdzony.
- Szkielety usług, Compose, hook sesji, pięć skilli i MCP Supabase read-only.
- B1: JWT, profil, odcinki/nearest/detail, oceny, komentarze i moderacja komentarzy;
  wspólne błędy, limity, healthcheck DB; testy offline i diagnostyka środowiska.
- Supabase online: tabele i RLS istnieją; sześć migracji B2 scalono z origin/main
  (93d01d9) do tego brancha. Seed pozostaje u B2.
- Integracje frontend/map, ai/service i backend/routing wycofano na prośbę B1.
  Na branchu pozostają wspólne szkielety FE/AI oraz implementacja B1.
- Współdzielone limity Redis, trwały wolumen i testy wielu klientów. GitHub Actions
  sprawdza backend, kompilację szkieletu AI oraz frontend build/lint.
- Branch opublikowany, draft PR #2, GitHub Actions PASS. Main chroniony: PR,
  1 akceptacja, checki backend/ai/frontend i zakaz force-push/usunięcia (także admin).

- 2026-10-05: własny graf tras (db/routing-graph, w main) i POST /route dla auta i roweru na grafie
  (backend/graph-routing). Piesi też z grafu, po drogach (db/foot-network, backend/foot-routing); ORS i mock usunięte.

## TODO

- Piesi faza 2 (ścieżki w parkach) tylko w razie potrzeby; parkingi przy celu i trasy alternatywne w grafie;
  przeszkody i pora dnia w trasach są gotowe (backend/obstacles-time-of-day);
  frontend/routing: wybór A→B, suwaki wag, lokalizacja użytkownika jako start (FE); instrukcja
  podłączenia dla FE jest w skillu frontend, sekcja „Trasy: co podłączyć”.
- backend/b1-howoo: sekrety DB/service_role i test rzeczywistego JWT/zapisów odroczone
  na prośbę użytkownika. Kontenery demo działają; DB health=503 bez konfiguracji.
- db/seed-krakow (B2): seed Krakowa i weryfikacja harmonogramu segment_stats.
- backend/parkingi (B2): GET /parking. Przeszkody gotowe; zdjęcia (upload, galeria, EXIF, miniatury) zrobione w backend/ai-integration.
- backend/ai-integration (AI): podsumowania i cache działają (patrz skill ai); routing mock wymienić na rzeczywisty provider
  i źródło segmentów PostGIS. Integracja serwisu AI/routingu poza zakresem B1.
- frontend/* (FE): mapa, Auth/formularze i PWA na branchach FE.
- setup/repo: sprawdzić uprawnienia zespołu; ochrona main gotowa.
