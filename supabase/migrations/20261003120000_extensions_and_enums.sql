-- Extensions and enum types shared with docs/CONTRACT.md (section 3).

create extension if not exists postgis with schema extensions;

create type public.time_of_day as enum ('morning', 'day', 'evening', 'night');
create type public.obstacle_type as enum ('roadwork', 'closure', 'pothole', 'accident', 'other');
create type public.content_status as enum ('visible', 'hidden');
