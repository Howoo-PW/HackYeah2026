-- pgRouting for the own router (docs/ROUTING_GRAPH.md). Only the extension: the graph tables
-- (nodes, edges, oneway, profiles) are built by B2 in a separate migration.

create extension if not exists pgrouting with schema extensions;
