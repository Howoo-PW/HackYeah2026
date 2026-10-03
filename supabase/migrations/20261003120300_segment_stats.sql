-- Aggregated scores per segment (map coloring) and per segment + time of day.
-- Only segments with at least one rating have a row.

create materialized view public.segment_stats as
select
  segment_id,
  round(avg(surface), 2)::real as surface,
  round(avg(views), 2)::real as views,
  round(avg(safety), 2)::real as safety,
  round(avg(traffic), 2)::real as traffic,
  round(avg(parking), 2)::real as parking,
  count(*)::integer as ratings_count,
  max(created_at) as last_rating_at
from public.ratings
group by segment_id;
create unique index segment_stats_pk on public.segment_stats (segment_id);

create materialized view public.segment_stats_by_time as
select
  segment_id,
  time_of_day,
  round(avg(surface), 2)::real as surface,
  round(avg(views), 2)::real as views,
  round(avg(safety), 2)::real as safety,
  round(avg(traffic), 2)::real as traffic,
  round(avg(parking), 2)::real as parking,
  count(*)::integer as ratings_count
from public.ratings
group by segment_id, time_of_day;
create unique index segment_stats_by_time_pk on public.segment_stats_by_time (segment_id, time_of_day);

grant select on public.segment_stats, public.segment_stats_by_time to anon, authenticated;

-- Refresh helper; the backend may call it via RPC after a write burst.
create function public.refresh_segment_stats()
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  refresh materialized view concurrently public.segment_stats;
  refresh materialized view concurrently public.segment_stats_by_time;
end;
$$;
revoke execute on function public.refresh_segment_stats() from public, anon, authenticated;
grant execute on function public.refresh_segment_stats() to service_role;

-- Periodic refresh every 2 minutes.
create extension if not exists pg_cron;
select cron.schedule(
  'refresh-segment-stats',
  '*/2 * * * *',
  $$select public.refresh_segment_stats()$$
);
