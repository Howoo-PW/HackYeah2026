-- Marks demo comments written by seed scripts, so they can be told apart and removed in one go:
--   delete from public.comments where seed_tag = 'vistula-2026-10';
-- Real comments written by the backend leave it null. See scripts/seed_vistula.py.
alter table public.comments add column if not exists seed_tag text;
create index if not exists comments_seed_tag_idx on public.comments (seed_tag) where seed_tag is not null;
