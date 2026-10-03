-- Row Level Security. Writes go only through the backend (service_role bypasses RLS).
-- anon/authenticated get read-only access to public data.

alter table public.profiles enable row level security;
alter table public.segments enable row level security;
alter table public.ratings enable row level security;
alter table public.comments enable row level security;
alter table public.obstacles enable row level security;
alter table public.parking_spots enable row level security;
alter table public.segment_photos enable row level security;
alter table public.segment_summaries enable row level security;

-- Defense in depth: no write privileges for client roles at all.
revoke insert, update, delete, truncate on
  public.profiles, public.segments, public.ratings, public.comments,
  public.obstacles, public.parking_spots, public.segment_photos, public.segment_summaries
from anon, authenticated;

create policy "profiles: read own" on public.profiles
  for select to authenticated using ((select auth.uid()) = id);

create policy "segments: public read" on public.segments
  for select to anon, authenticated using (true);

create policy "parking_spots: public read" on public.parking_spots
  for select to anon, authenticated using (true);

create policy "ratings: read own" on public.ratings
  for select to authenticated using ((select auth.uid()) = user_id);

create policy "comments: public read visible" on public.comments
  for select to anon, authenticated using (status = 'visible');

create policy "obstacles: public read active" on public.obstacles
  for select to anon, authenticated
  using (valid_until is null or valid_until > now());

create policy "segment_photos: public read visible" on public.segment_photos
  for select to anon, authenticated using (status = 'visible');

create policy "segment_summaries: public read" on public.segment_summaries
  for select to anon, authenticated using (true);
