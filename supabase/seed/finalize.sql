select setval(pg_get_serial_sequence('public.segments', 'id'), (select max(id) from public.segments));
select setval(pg_get_serial_sequence('public.parking_spots', 'id'), coalesce((select max(id) from public.parking_spots), 1));
