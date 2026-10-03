-- Fragments (segment_groups, 300-700 m) for the routing graph. The graph stays fine-grained (every
-- junction can be turned at); an edge reaches its rating fragment through its segment. Because it is
-- a view there is nothing to keep in sync after rebuild_routing_graph() or after the fragments are
-- rebuilt (scripts/build_segment_groups.py). Edges without a segment (about two thirds: roads that are
-- not in public.segments, e.g. service roads) have no fragment.

create view public.routing_edge_group with (security_invoker = true) as
select e.id as edge_id, s.group_id
from public.routing_edges e
join public.segments s on s.id = e.segment_id
where s.group_id is not null;

revoke all on public.routing_edge_group from anon, authenticated;
