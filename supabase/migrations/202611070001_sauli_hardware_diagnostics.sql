begin;

create table public.sauli_hardware_snapshots (
  device_id uuid primary key references public.kiosk_devices(id) on delete cascade,
  unit_id uuid not null references public.sauli_units(id) on delete restrict,
  snapshot jsonb not null,
  received_at timestamptz not null default now()
);
create index sauli_hardware_snapshots_unit_idx on public.sauli_hardware_snapshots(unit_id,received_at desc);

create table public.sauli_hardware_commands (
  id uuid primary key default gen_random_uuid(),
  device_id uuid not null references public.kiosk_devices(id) on delete cascade,
  unit_id uuid not null references public.sauli_units(id) on delete restrict,
  action text not null check (action in ('pulse_pocket','pulse_medium')),
  status text not null default 'pending' check (status in ('pending','claimed','acked','failed')),
  expires_at timestamptz not null,
  claimed_at timestamptz,
  acknowledged_at timestamptz,
  result_code text,
  created_at timestamptz not null default now()
);
create index sauli_hardware_commands_claim_idx on public.sauli_hardware_commands(device_id,status,expires_at);

-- A command is claimed once. A response lost in transit does not cause another pulse.
create function public.sauli_claim_hardware_commands(p_device_id uuid, p_unit_id uuid)
returns setof public.sauli_hardware_commands
language plpgsql security invoker set search_path = '' as $$
begin
  return query
  update public.sauli_hardware_commands c set status = 'claimed', claimed_at = now()
  where c.id in (
    select q.id from public.sauli_hardware_commands q
    where q.device_id = p_device_id and q.unit_id = p_unit_id
      and q.status = 'pending' and q.expires_at > now()
    order by q.created_at
    limit 4 for update skip locked
  ) returning c.*;
end $$;

alter table public.sauli_hardware_snapshots enable row level security;
alter table public.sauli_hardware_commands enable row level security;
revoke all on public.sauli_hardware_snapshots, public.sauli_hardware_commands from anon, authenticated;
revoke all on function public.sauli_claim_hardware_commands(uuid,uuid) from public, anon, authenticated;
grant all on public.sauli_hardware_snapshots, public.sauli_hardware_commands to service_role;
grant execute on function public.sauli_claim_hardware_commands(uuid,uuid) to service_role;

commit;
