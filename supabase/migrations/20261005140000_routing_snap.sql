-- Where find_route() would start/end for a given point: the nearest node of the profile's main
-- (strongly connected) network, and how far it is. The backend uses the distance to refuse
-- points that are not near a road (like the external engine does for points > 350 m away).

create function public.routing_snap(p_profile text, p_lon double precision, p_lat double precision)
returns table (node_id bigint, distance_m double precision)
language plpgsql stable
set search_path = public, extensions
as $$
declare
  v_pf text;
  v_pt extensions.geometry := st_setsrid(st_makepoint(p_lon, p_lat), 4326);
begin
  if p_profile = 'driving-car' then v_pf := 'car';
  elsif p_profile = 'cycling-regular' then v_pf := 'bike';
  else raise exception 'unsupported profile: %', p_profile using errcode = '22023';
  end if;

  return query execute format(
    'select id, st_distance(geom::geography, $1::geography) from public.routing_nodes
     where %s_main order by geom <-> $1 limit 1', v_pf)
    using v_pt;
end;
$$;
revoke execute on function public.routing_snap(text, double precision, double precision) from public, anon, authenticated;
