-- Private bucket for segment photos. No storage policies on purpose:
-- only the backend (service_role) reads/writes and hands out signed URLs.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'segment-photos',
  'segment-photos',
  false,
  5242880,  -- 5 MB, see CONTRACT.md 413 FILE_TOO_LARGE
  array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do nothing;
