-- Map layer for zoomed-out views: one row per fragment (segment_groups) with its merged, simplified
-- geometry and length-weighted effective scores, so the whole city is about 5 000 features instead of
-- 22 000 segments (GET /groups?bbox=). Refreshed together with the other statistics.

create materialized view public.fragment_map as
select
  g.id as group_id,
  g.name, g.highway, g.length_m, g.segments_count,
  st_multi(st_simplifypreservetopology(st_collect(s.geom), 0.00003)) as geom,   -- about 3 m
  (sum(ss.surface * s.length_m) filter (where ss.surface is not null)
     / nullif(sum(s.length_m) filter (where ss.surface is not null), 0))::real as surface,
  (sum(ss.views * s.length_m) filter (where ss.views is not null)
     / nullif(sum(s.length_m) filter (where ss.views is not null), 0))::real as views,
  (sum(ss.safety * s.length_m) filter (where ss.safety is not null)
     / nullif(sum(s.length_m) filter (where ss.safety is not null), 0))::real as safety,
  (sum(ss.traffic * s.length_m) filter (where ss.traffic is not null)
     / nullif(sum(s.length_m) filter (where ss.traffic is not null), 0))::real as traffic,
  (sum(ss.parking * s.length_m) filter (where ss.parking is not null)
     / nullif(sum(s.length_m) filter (where ss.parking is not null), 0))::real as parking,
  coalesce(sum(ss.ratings_count), 0)::integer as ratings_count,
  case when bool_or(ss.source = 'own') then 'own'
       when bool_or(ss.segment_id is not null) then 'group'
       else 'none' end as source
from public.segment_groups g
join public.segments s on s.group_id = g.id
left join public.segment_scores ss on ss.segment_id = s.id
group by g.id;

create unique index fragment_map_pk on public.fragment_map (group_id);
create index fragment_map_geom_idx on public.fragment_map using gist (geom);
revoke all on public.fragment_map from anon, authenticated;

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
  refresh materialized view concurrently public.fragment_map;
  refresh materialized view concurrently public.routing_graph;
end;
$$;
