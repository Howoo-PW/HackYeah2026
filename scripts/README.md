# Skrypty

Narzędzia jednorazowe i diagnostyczne, uruchamiane z katalogu repo (`python scripts/<plik>.py`). Baza i klucze
z `.env` (wspólne funkcje w `_common.py`: `SUPABASE_DB_URL` z `.env` albo ze zmiennej środowiska). Testy: `cd scripts && python -m pytest -q`.

| Skrypt | Do czego |
|---|---|
| `verify_env.py` | Diagnostyka checkoutu bez wypisywania sekretów; `--start` buduje i uruchamia Compose |
| `create_dev_admin.py` | Konto admina w Supabase Auth, tylko `APP_ENV=dev` |
| `apply_migration.py` | Stosuje jeden plik z `supabase/migrations/` w jednej transakcji |
| `import_osm.py` | Overpass → odcinki i parkingi → pliki `supabase/seed/*.sql` |
| `load_seed.py` | Ładuje `supabase/seed/*.sql` do bazy (idempotentnie) |
| `build_segment_groups.py` | Buduje fragmenty ocen 300–700 m (`fragments.py`) i seed `groups_*.sql`; `--apply` zapisuje w bazie |
| `load_osm_routing.py`, `load_osm_foot.py` | Sieć OSM dla auta, roweru i pieszych do `public.osm_ways` (reguły tagów w `osm_access.py`) |
| `check_graph.py` | Spójność grafu dróg (tylko odczyt) |
| `embed_comments.py` | Wektory komentarzy przez serwis AI (wyszukiwanie po sensie) |
| `seed_zones.py`, `seed_vistula.py` | Syntetyczne oceny i komentarze demo (`--dry-run`, `--apply`, `--remove`) |

Biblioteki skryptów: `_common.py` (root repo, `.env`, adres bazy), `fragments.py` (grupowanie odcinków), `osm_access.py` (tagi OSM → kierunki i prędkości).
