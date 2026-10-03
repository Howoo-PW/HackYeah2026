-- Marks synthetic demo ratings so that they can be told apart from real ones and removed:
--   delete from public.ratings where seed_tag = 'zones-2026-10';
-- Real ratings written by the backend leave it null. See scripts/seed_zones.py.

alter table public.ratings add column seed_tag text;
create index ratings_seed_tag_idx on public.ratings (seed_tag) where seed_tag is not null;
