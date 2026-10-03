-- Effective scores in SQL, for the router's cost function and for anything that reads scores in the
-- database. Same rule as backend/app/grouping.py (effective_scores), kept in sync by a test:
--   own ratings (worth K_SEGMENT = 2 group ratings), else the rest of the group's mean pulled
--   toward the road-type mean (K_GROUP = 3 ratings). Only segments with a score have a row.

create function public.effective_score(
  own_n bigint, own_sum numeric, grp_n bigint, grp_sum numeric, hw_n bigint, hw_sum numeric
) returns numeric
language sql immutable parallel safe
set search_path = ''
as $$
  with p as (
    select case when hw_n > 0 then hw_sum / hw_n end as prior,
           greatest(grp_n - own_n, 0) as rest_n,
           greatest(grp_sum - own_sum, 0) as rest_sum
  ), m as (
    select prior, rest_n, rest_sum,
           case when rest_n > 0 then
             case when prior is not null then (rest_sum + 3 * prior) / (rest_n + 3) else rest_sum / rest_n end
           end as rest
    from p
  )
  select case
    when own_n > 0 then round((own_sum + 2 * coalesce(rest, prior, own_sum / own_n)) / (own_n + 2), 2)
    else round(rest, 2)
  end
  from m
$$;

create materialized view public.segment_scores as
with own as (
  select segment_id,
    count(surface) as surface_n, coalesce(sum(surface), 0) as surface_s,
    count(views) as views_n, coalesce(sum(views), 0) as views_s,
    count(safety) as safety_n, coalesce(sum(safety), 0) as safety_s,
    count(traffic) as traffic_n, coalesce(sum(traffic), 0) as traffic_s,
    count(parking) as parking_n, coalesce(sum(parking), 0) as parking_s,
    count(*) as ratings_count
  from public.ratings group by segment_id
), grp as (
  select s.group_id,
    count(r.surface) as surface_n, coalesce(sum(r.surface), 0) as surface_s,
    count(r.views) as views_n, coalesce(sum(r.views), 0) as views_s,
    count(r.safety) as safety_n, coalesce(sum(r.safety), 0) as safety_s,
    count(r.traffic) as traffic_n, coalesce(sum(r.traffic), 0) as traffic_s,
    count(r.parking) as parking_n, coalesce(sum(r.parking), 0) as parking_s
  from public.ratings r join public.segments s on s.id = r.segment_id
  where s.group_id is not null group by s.group_id
), hw as (
  select s.highway,
    count(r.surface) as surface_n, coalesce(sum(r.surface), 0) as surface_s,
    count(r.views) as views_n, coalesce(sum(r.views), 0) as views_s,
    count(r.safety) as safety_n, coalesce(sum(r.safety), 0) as safety_s,
    count(r.traffic) as traffic_n, coalesce(sum(r.traffic), 0) as traffic_s,
    count(r.parking) as parking_n, coalesce(sum(r.parking), 0) as parking_s
  from public.ratings r join public.segments s on s.id = r.segment_id group by s.highway
), joined as (
  select s.id as segment_id, s.group_id,
    coalesce(own.ratings_count, 0)::integer as ratings_count,
    -- evidence: own ratings plus half of the neighbours' ratings, best dimension
    greatest(
      coalesce(own.surface_n, 0) + 0.5 * greatest(coalesce(grp.surface_n, own.surface_n, 0) - coalesce(own.surface_n, 0), 0),
      coalesce(own.views_n, 0) + 0.5 * greatest(coalesce(grp.views_n, own.views_n, 0) - coalesce(own.views_n, 0), 0),
      coalesce(own.safety_n, 0) + 0.5 * greatest(coalesce(grp.safety_n, own.safety_n, 0) - coalesce(own.safety_n, 0), 0),
      coalesce(own.traffic_n, 0) + 0.5 * greatest(coalesce(grp.traffic_n, own.traffic_n, 0) - coalesce(own.traffic_n, 0), 0),
      coalesce(own.parking_n, 0) + 0.5 * greatest(coalesce(grp.parking_n, own.parking_n, 0) - coalesce(own.parking_n, 0), 0)
    ) as evidence,
    public.effective_score(coalesce(own.surface_n, 0), coalesce(own.surface_s, 0), coalesce(grp.surface_n, own.surface_n, 0), coalesce(grp.surface_s, own.surface_s, 0), coalesce(hw.surface_n, 0), coalesce(hw.surface_s, 0)) as surface,
    public.effective_score(coalesce(own.views_n, 0), coalesce(own.views_s, 0), coalesce(grp.views_n, own.views_n, 0), coalesce(grp.views_s, own.views_s, 0), coalesce(hw.views_n, 0), coalesce(hw.views_s, 0)) as views,
    public.effective_score(coalesce(own.safety_n, 0), coalesce(own.safety_s, 0), coalesce(grp.safety_n, own.safety_n, 0), coalesce(grp.safety_s, own.safety_s, 0), coalesce(hw.safety_n, 0), coalesce(hw.safety_s, 0)) as safety,
    public.effective_score(coalesce(own.traffic_n, 0), coalesce(own.traffic_s, 0), coalesce(grp.traffic_n, own.traffic_n, 0), coalesce(grp.traffic_s, own.traffic_s, 0), coalesce(hw.traffic_n, 0), coalesce(hw.traffic_s, 0)) as traffic,
    public.effective_score(coalesce(own.parking_n, 0), coalesce(own.parking_s, 0), coalesce(grp.parking_n, own.parking_n, 0), coalesce(grp.parking_s, own.parking_s, 0), coalesce(hw.parking_n, 0), coalesce(hw.parking_s, 0)) as parking
  from public.segments s
  left join own on own.segment_id = s.id
  left join grp on grp.group_id = s.group_id
  left join hw on hw.highway = s.highway
  where own.segment_id is not null or grp.group_id is not null
)
select segment_id, group_id,
  surface::real as surface, views::real as views, safety::real as safety,
  traffic::real as traffic, parking::real as parking,
  ratings_count,
  case when ratings_count > 0 then 'own' else 'group' end as source,
  case when evidence >= 5 then 'high' when evidence >= 2 then 'medium' else 'low' end as confidence
from joined
where coalesce(surface, views, safety, traffic, parking) is not null;

create unique index segment_scores_pk on public.segment_scores (segment_id);
create index segment_scores_group_idx on public.segment_scores (group_id);
grant select on public.segment_scores to anon, authenticated;

-- Refresh together with the other statistics (the cron job calls this every 2 minutes).
create or replace function public.refresh_segment_stats()
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  refresh materialized view concurrently public.segment_stats;
  refresh materialized view concurrently public.segment_stats_by_time;
  refresh materialized view concurrently public.segment_scores;
end;
$$;
