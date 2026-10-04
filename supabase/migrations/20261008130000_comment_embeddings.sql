-- Meaning of comments as vectors (pgvector), for the assistant's search by description ("spokojna droga nad wodą").
-- Written only by the backend (it connects as the database owner); no policies, so the API roles cannot read or write it.
-- 1536 dimensions = OpenAI text-embedding-3-small; `model` records which model made a vector, so a change of model can be re-embedded.
create extension if not exists vector with schema extensions;

create table public.comment_embeddings (
  comment_id uuid primary key references public.comments (id) on delete cascade,
  embedding extensions.vector(1536) not null,
  model text not null,
  created_at timestamptz not null default now()
);
create index comment_embeddings_hnsw on public.comment_embeddings using hnsw (embedding extensions.vector_cosine_ops);
alter table public.comment_embeddings enable row level security;
revoke all on public.comment_embeddings from anon, authenticated;
