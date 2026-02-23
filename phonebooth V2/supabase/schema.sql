-- Core tables for Phonebooth backend (run in Supabase SQL editor)

create extension if not exists "pgcrypto";

create table if not exists public.users (
  id uuid primary key default gen_random_uuid(),
  supabase_user_id uuid not null unique,
  username varchar(64) not null,
  avatar_url varchar(512),
  created_at timestamptz not null default now()
);

create table if not exists public.servers (
  id uuid primary key default gen_random_uuid(),
  name varchar(100) not null,
  owner_id uuid not null references public.users(id) on delete cascade,
  created_at timestamptz not null default now()
);

create table if not exists public.server_members (
  id uuid primary key default gen_random_uuid(),
  server_id uuid not null references public.servers(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  role varchar(20) not null default 'member',
  joined_at timestamptz not null default now(),
  constraint uq_server_user unique (server_id, user_id)
);

create table if not exists public.channels (
  id uuid primary key default gen_random_uuid(),
  server_id uuid not null references public.servers(id) on delete cascade,
  name varchar(80) not null,
  channel_type varchar(20) not null default 'text',
  position integer not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  channel_id uuid not null references public.channels(id) on delete cascade,
  author_id uuid not null references public.users(id) on delete cascade,
  content text not null,
  created_at timestamptz not null default now(),
  edited_at timestamptz
);

create index if not exists idx_users_supabase_user_id on public.users(supabase_user_id);
create index if not exists idx_servers_owner_id on public.servers(owner_id);
create index if not exists idx_server_members_server_id on public.server_members(server_id);
create index if not exists idx_server_members_user_id on public.server_members(user_id);
create index if not exists idx_channels_server_id on public.channels(server_id);
create index if not exists idx_messages_channel_id on public.messages(channel_id);
create index if not exists idx_messages_author_id on public.messages(author_id);

-- Optional RLS defaults if your frontend also reads directly from Supabase.
-- The FastAPI backend should connect with service role or DB credentials and can bypass RLS as needed.
alter table public.users enable row level security;
alter table public.servers enable row level security;
alter table public.server_members enable row level security;
alter table public.channels enable row level security;
alter table public.messages enable row level security;

create policy if not exists users_self_read on public.users
for select using (supabase_user_id = auth.uid());

create policy if not exists users_self_update on public.users
for update using (supabase_user_id = auth.uid())
with check (supabase_user_id = auth.uid());

create policy if not exists servers_member_read on public.servers
for select using (
  exists (
    select 1
    from public.server_members sm
    join public.users u on u.id = sm.user_id
    where sm.server_id = servers.id and u.supabase_user_id = auth.uid()
  )
);

create policy if not exists channels_member_read on public.channels
for select using (
  exists (
    select 1
    from public.server_members sm
    join public.users u on u.id = sm.user_id
    where sm.server_id = channels.server_id and u.supabase_user_id = auth.uid()
  )
);

create policy if not exists messages_member_read on public.messages
for select using (
  exists (
    select 1
    from public.channels c
    join public.server_members sm on sm.server_id = c.server_id
    join public.users u on u.id = sm.user_id
    where c.id = messages.channel_id and u.supabase_user_id = auth.uid()
  )
);

-- Discord bot config and call state tables
create table if not exists public.guild_bot_configs (
  guild_id bigint primary key,
  mode varchar(10) not null default 'quick' check (mode in ('quick', 'more')),
  updated_at timestamptz not null default now()
);

create table if not exists public.guild_allowed_channels (
  guild_id bigint not null references public.guild_bot_configs(guild_id) on delete cascade,
  channel_id bigint not null,
  added_at timestamptz not null default now(),
  primary key (guild_id, channel_id)
);

create table if not exists public.call_wait_queue (
  guild_id bigint not null,
  user_id bigint not null,
  channel_id bigint not null,
  queued_at timestamptz not null default now(),
  primary key (guild_id, user_id)
);

create table if not exists public.active_calls (
  guild_id bigint not null,
  user_a_id bigint not null,
  user_b_id bigint not null,
  started_at timestamptz not null default now(),
  constraint uq_active_pair unique (guild_id, user_a_id, user_b_id),
  constraint ck_not_self_call check (user_a_id <> user_b_id)
);

create index if not exists idx_call_wait_queue_guild_queued_at on public.call_wait_queue(guild_id, queued_at);
create index if not exists idx_active_calls_guild_user_a on public.active_calls(guild_id, user_a_id);
create index if not exists idx_active_calls_guild_user_b on public.active_calls(guild_id, user_b_id);

-- Active calls should never duplicate reversed user pairs.
create unique index if not exists uq_active_pair_normalized
  on public.active_calls (guild_id, least(user_a_id, user_b_id), greatest(user_a_id, user_b_id));
