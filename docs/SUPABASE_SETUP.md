# Baza od nowa: własny projekt Supabase

Przepis na postawienie pustej bazy tak, żeby aplikacja (`docker-compose.jury.yml` albo tryb deweloperski) działała na Twoim projekcie. Używa istniejących narzędzi z repo; schemat jest wyłącznie w `supabase/migrations/`.

> Ta ścieżka nie była jeszcze przechodzona od zera na pustym projekcie. Każdy krok korzysta z narzędzi sprawdzonych na bazie zespołu, ale kolejność i liczby poniżej pochodzą z dokumentacji (`docs/ROUTING_DB_STATE.md`, `docs/ROUTING_GRAPH.md`) i kodu. Jeśli coś się rozjedzie, napisz, a poprawimy przepis.

## 0. Wymagania na swoim komputerze

- Python 3.12+ i `pip install "psycopg[binary]"` (skrypty łączą się z bazą bezpośrednio); do kroku 6 jeszcze `httpx`.
- Internet (Overpass pobiera drogi Krakowa; pierwsze pobranie trwa kilka–kilkanaście minut, wynik trafia do `data/osm_cache/`).
- Docker Desktop, tylko do uruchomienia aplikacji na końcu.

## 1. Projekt Supabase

1. Na [supabase.com](https://supabase.com) załóż nowy projekt (region najbliżej, np. Frankfurt) i zapisz **hasło bazy**.
2. Skopiuj `.env.example` do `.env` i wpisz wartości z tabeli w [README](../README.md#bez-dołączonej-konfiguracji-własne-usługi): `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_DB_URL`, `INTERNAL_API_KEY` (i klucz AI).
3. Rozszerzenia `postgis`, `pgrouting`, `vector` i `pg_cron` włączają się same migracjami. Jeśli któraś migracja zgłosi brak rozszerzenia, włącz je ręcznie w Supabase: Database → Extensions, i powtórz krok.

`SUPABASE_DB_URL` z poolera w trybie transakcyjnym (port 6543) jest właściwy dla aplikacji. Skrypty ładujące używają tego samego adresu; gdyby zgłosiły błąd „prepared statement”, na czas ładowania podstaw adres poolera w trybie sesji (port 5432).

## 2. Schemat (migracje)

Wszystkie pliki z `supabase/migrations/`, w kolejności nazw (każdy w jednej transakcji, wszystko albo nic). Z katalogu repo:

```sh
# bash
for f in supabase/migrations/*.sql; do python scripts/apply_migration.py "$f" || break; done
```
```powershell
# PowerShell
Get-ChildItem supabase/migrations/*.sql | Sort-Object Name | ForEach-Object { python scripts/apply_migration.py $_.FullName; if ($LASTEXITCODE) { break } }
```

Powstają: tabele, RLS, widoki ocen, prywatny bucket `segment-photos`, graf tras (`osm_ways`, `routing_*`, `rebuild_routing()`), przeszkody i pora dnia, wektory komentarzy. Przy błędzie popraw przyczynę i uruchom ponownie od pliku, który padł (poprzednie są już zastosowane).

## 3. Odcinki i parkingi Krakowa

```sh
python scripts/load_seed.py
```

Ładuje `supabase/seed/segments_*.sql` i `parking.sql` (idempotentnie, można powtórzyć). Oczekiwane: około 22 664 odcinków i parkingi.

## 4. Fragmenty ocen (grupy odcinków)

Pliki `groups_*.sql` nie są częścią `load_seed.py`; `groups_001.sql` wstawia fragmenty, kolejne przypisują je odcinkom. Muszą pójść po kroku 3, w kolejności nazw:

```sh
for f in supabase/seed/groups_*.sql; do python scripts/apply_migration.py "$f" || break; done
```

Oczekiwane: około 5 053 fragmentów w `segment_groups`.

## 5. Sieć dróg i graf tras

```sh
python scripts/load_osm_routing.py     # drogi dla auta, roweru i pieszych do osm_ways (Overpass, 8 kafelków, cache w data/)
python scripts/load_osm_foot.py        # ulice tylko dla pieszych (np. Stare Miasto)
```

Potem w SQL (Supabase → SQL Editor):

```sql
select * from public.rebuild_routing();
```

Budowa grafu chwilę trwa i zwraca liczbę krawędzi oraz spójność (cel: około 96% długości w jednej silnie spójnej składowej). Szczegóły: [ROUTING_GRAPH.md](ROUTING_GRAPH.md).

## 6. Odświeżenie widoków

Widoki materializowane powstały puste. Po załadowaniu danych odśwież je (SQL Editor):

```sql
select public.refresh_segment_stats();
```

Funkcja odświeża statystyki ocen, `segment_scores`, `fragment_map` i `routing_graph` (potem robi to samo cyklicznie `pg_cron` co 2 minuty). Gdyby zgłosiła brak uprawnień, wykonaj po kolei `refresh materialized view public.segment_stats;`, `public.segment_scores`, `public.fragment_map`, `public.routing_graph`.

## 7. Sprawdzenie

```sql
select (select count(*) from public.segments)       as segments,
       (select count(*) from public.segment_groups) as fragments,
       (select count(*) from public.osm_ways)       as ways,
       (select count(*) from public.routing_edges)  as edges;
```

Wszystkie wartości mają być większe od zera. Następnie uruchom aplikację (`docker compose --env-file .env -f docker-compose.jury.yml up --build --wait --wait-timeout 180`) i otwórz http://localhost:8000/api/v1/health: `database`, `ai_service` i `routing` mają być `ok`. Na mapie (http://localhost:5173) odcinki będą szare, dopóki nie pojawią się oceny.

## 8. Opcjonalnie: konto admina i dane demo

- Konto admina (tylko `APP_ENV=dev`, dane w `.env`: `DEV_ADMIN_EMAIL`, `DEV_ADMIN_PASSWORD`): `python scripts/create_dev_admin.py`.
- Przykładowe oceny i komentarze (`--dry-run` pokazuje plan, `--apply` zapisuje): `python scripts/seed_zones.py --apply`, `python scripts/seed_vistula.py --apply`. Obie czytają użytkowników z tabeli `profiles`, więc **najpierw zarejestruj w aplikacji przynajmniej jedno konto**.
- Wektory komentarzy dla wyszukiwania po sensie (wymaga działającego serwisu AI z kluczem): `python scripts/embed_comments.py`.

## Wyczyszczenie istniejącej bazy (tylko własny projekt)

Prościej założyć nowy projekt. Jeśli musisz wyczyścić własny projekt, w SQL Editor (kasuje wszystkie dane w schemacie `public`, **nieodwracalnie**; pozostają konta w Auth, rozszerzenia i pliki w Storage):

```sql
drop schema public cascade;
create schema public;
grant usage on schema public to postgres, anon, authenticated, service_role;
grant all on schema public to postgres, service_role;
```

i wróć do kroku 2. **Nigdy nie rób tego na projekcie zespołu ani na bazie, z której korzysta jury.**
