-- Aoryn minimal auth/profile setup for Supabase.
-- This keeps cloud data limited to identity and the smallest possible profile.

create table if not exists public.profiles (
  id uuid primary key,
  email text not null,
  display_name text not null default '',
  created_at timestamptz not null default timezone('utc', now())
);

alter table public.profiles
  alter column display_name set default '',
  alter column created_at set default timezone('utc', now());

update public.profiles
set display_name = coalesce(display_name, '')
where display_name is null;

alter table public.profiles
  drop constraint if exists profiles_id_fkey;

alter table public.profiles
  add constraint profiles_id_fkey
  foreign key (id) references auth.users(id) on delete cascade;

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, display_name, created_at)
  values (
    new.id,
    coalesce(new.email, ''),
    coalesce(new.raw_user_meta_data ->> 'display_name', ''),
    coalesce(new.created_at, timezone('utc', now()))
  )
  on conflict (id) do update
    set email = excluded.email,
        display_name = case
          when coalesce(public.profiles.display_name, '') = '' then excluded.display_name
          else public.profiles.display_name
        end;
  return new;
exception
  when others then
    raise log 'handle_new_user failed for %: %', new.id, sqlerrm;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;

create trigger on_auth_user_created
after insert on auth.users
for each row
execute function public.handle_new_user();

alter table public.profiles enable row level security;

drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own
on public.profiles
for select
to authenticated
using (auth.uid() = id);

drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own
on public.profiles
for update
to authenticated
using (auth.uid() = id)
with check (auth.uid() = id);

-- No insert policy on purpose:
-- clients must create accounts through Supabase Auth so the trigger writes profiles.
