---
name: database
description: Schemat, migracje, PostGIS, RLS i seed Supabase. Właściciel B2.
---

# Database

Czytaj project-overview, docs/CONTRACT.md i plan sekcja 3. Supabase online,
ref lsfpirkqdtjkcaujnsde. PostGIS w extensions, SRID 4326. Nie twórz lokalnej bazy.

Zmiany schematu w supabase/migrations/, nawet gdy stosujesz przez MCP.
MCP projektu jest read-only; zapis w bazie wymaga świadomie wybranego połączenia.
RLS na wszystkich tabelach publicznych; użytkownicy nie zapisują bez backendu.
Service_role/DB hasło nigdy w frontendzie. Role w auth.users.raw_app_meta_data.
Indeksy GiST na geom, indeksy FK i unique ocen (user_id,segment_id,rated_on).
Bucket segment-photos prywatny, zdjęcia przez backend z signed URL.
Widoki powinny respektować rzeczywisty model uprawnień; nie dodawaj
SECURITY DEFINER jako obejścia problemu dostępu.

Po zmianie dodaj dokumentację SQL/publicznych funkcji, zaktualizuj strukturę,
Stan i TODO tutaj oraz w overview i dziennik B2. Nie edytuj kontraktu przy okazji.

## Stan

- 2026-10-03: online istnieją osiem tabel, RLS, segment_stats i PostGIS.
- ratings ma rated_on i unique(user_id,segment_id,rated_on), zgodne z backendem.
- B1 nie dodaje ani nie stosuje migracji; DB pozostaje własnością B2.
- Sześć migracji B2 z origin/main (93d01d9) jest już w tym branchu.

## TODO

- db/schema: migracje scalone; dalsza weryfikacja uprawnień i harmonogramów u B2.
- db/seed-krakow: import OSM, podział odcinków <=300 m, parkingi i dane demo.
- Harmonogram odświeżania segment_stats; pgRouting dopiero gdy używany.
- backend/photos, backend/obstacles-parking: implementacja i integracja routerów.
