-- AI Investment Dashboard — Supabase schema
-- Apply after the Supabase project is connected.

create extension if not exists pgcrypto;

create table if not exists public.app_members (
  email text primary key,
  role text not null check (role in ('owner','viewer')),
  display_name text,
  created_at timestamptz not null default now()
);

create table if not exists public.holdings (
  id uuid primary key default gen_random_uuid(),
  ticker text not null,
  entry_date date,
  entry_avg numeric,
  strategy text,
  notes text,
  created_by uuid default auth.uid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.trades (
  id uuid primary key default gen_random_uuid(),
  ticker text not null,
  entry_date date not null,
  entry_avg numeric not null,
  exit_date date,
  exit_avg numeric,
  strategy text,
  exit_reason text,
  notes text,
  created_by uuid default auth.uid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((exit_date is null and exit_avg is null) or (exit_date is not null and exit_avg is not null))
);

create or replace function public.is_member()
returns boolean language sql stable security definer set search_path=public as $$
  select exists(
    select 1 from public.app_members m
    where lower(m.email)=lower(coalesce(auth.jwt()->>'email',''))
  );
$$;

create or replace function public.is_owner()
returns boolean language sql stable security definer set search_path=public as $$
  select exists(
    select 1 from public.app_members m
    where lower(m.email)=lower(coalesce(auth.jwt()->>'email','')) and m.role='owner'
  );
$$;

alter table public.app_members enable row level security;
alter table public.holdings enable row level security;
alter table public.trades enable row level security;

-- Members may read the allowlist only for their own row. Owners may read all.
drop policy if exists "members_read_own_or_owner_all" on public.app_members;
create policy "members_read_own_or_owner_all" on public.app_members for select to authenticated
using (lower(email)=lower(coalesce(auth.jwt()->>'email','')) or public.is_owner());

-- Owner manages member allowlist.
drop policy if exists "owner_manage_members" on public.app_members;
create policy "owner_manage_members" on public.app_members for all to authenticated
using (public.is_owner()) with check (public.is_owner());

-- All approved members can read portfolio data.
drop policy if exists "members_read_holdings" on public.holdings;
create policy "members_read_holdings" on public.holdings for select to authenticated
using (public.is_member());

drop policy if exists "members_read_trades" on public.trades;
create policy "members_read_trades" on public.trades for select to authenticated
using (public.is_member());

-- Only owner can mutate portfolio data.
drop policy if exists "owner_write_holdings" on public.holdings;
create policy "owner_write_holdings" on public.holdings for all to authenticated
using (public.is_owner()) with check (public.is_owner());

drop policy if exists "owner_write_trades" on public.trades;
create policy "owner_write_trades" on public.trades for all to authenticated
using (public.is_owner()) with check (public.is_owner());

-- Seed MU and NOW as current holdings after you fill actual entry data in the app.
