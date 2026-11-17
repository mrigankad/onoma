"use client";

import { useEffect, useState } from "react";
import { api, canDo, Me } from "@/lib/api";
import { useMe } from "@/components/me";
import { Button, Card, cx, Empty, ErrorNote } from "@/components/ui";

type Role = Me["role"];
type Row = Me & { created_at: string };
const ROLES: { id: Role; hint: string }[] = [
  { id: "viewer", hint: "Search and browse" },
  { id: "steward", hint: "Decide suggestions, edit names, upload data" },
  { id: "admin", hint: "Packs, agents and people" },
];

function RolePills({ value, onChange, disabled }: { value: Role; onChange: (r: Role) => void; disabled?: boolean }) {
  return (
    <div role="radiogroup" aria-label="Role" className="flex rounded-full bg-surface-2 p-1">
      {ROLES.map((r) => (
        <button key={r.id} type="button" role="radio" aria-checked={value === r.id} title={r.hint} disabled={disabled}
          onClick={() => onChange(r.id)}
          className={cx("rounded-full px-3.5 py-1.5 text-[13px] capitalize transition-colors disabled:cursor-not-allowed",
            value === r.id ? "bg-ink text-white" : "text-muted hover:text-ink")}>
          {r.id}
        </button>
      ))}
    </div>
  );
}

export default function Users() {
  const me = useMe();
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [form, setForm] = useState({ email: "", name: "", password: "", role: "viewer" as Role });

  const load = () => api.users().then(setRows).catch((e) => setError(e.message));
  useEffect(() => { if (canDo(me, "admin")) load(); }, [me]);

  const change = async (id: number, role: Role) => {
    setError("");
    try {
      await api.setRole(id, role);
      setRows((rs) => rs.map((r) => (r.id === id ? { ...r, role } : r)));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const u = await api.addUser(form);
      setNote(`${u.email} can sign in now as ${u.role}.`);
      setForm({ email: "", name: "", password: "", role: "viewer" });
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  if (me && !canDo(me, "admin")) {
    return <Card className="mx-auto max-w-[640px]"><Empty title="Admins only" body="Ask a workspace admin to change your role." /></Card>;
  }
  const field = "min-w-0 rounded-full bg-surface-2 px-5 py-3 text-sm outline-none focus:ring-2 focus:ring-primary";

  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-6">
      <div className="flex flex-col gap-2">
        <span className="text-[13px] text-muted">Settings · Users</span>
        <h1 className="display text-[40px] leading-[44px]">Who can change the vocabulary</h1>
      </div>
      {error && <ErrorNote error={error} />}
      {note && <div role="status" className="rounded-[20px] bg-primary-tint px-5 py-3.5 text-sm text-primary">{note}</div>}

      {me?.id === 0 && (
        <Card className="p-6 text-sm leading-6">
          Sign-in is off: anyone who can reach this engine acts as an admin. Adding the first person below turns it on,
          so add yourself as an admin first.
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <Card className="flex flex-col p-2.5">
          {rows.length === 0 && <p className="p-5 text-sm text-muted">No accounts yet.</p>}
          {rows.map((r) => (
            <div key={r.id} className="flex flex-wrap items-center gap-4 rounded-[20px] p-4 hover:bg-surface-2/60">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary-tint text-xs font-medium text-primary">
                {(r.name || r.email).slice(0, 2).toUpperCase()}
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-sm">{r.name}{r.id === me?.id && <span className="text-muted"> · you</span>}</span>
                <span className="truncate text-xs text-muted">{r.email}</span>
              </span>
              <RolePills value={r.role} onChange={(role) => change(r.id, role)} />
            </div>
          ))}
        </Card>

        <Card className="h-fit p-6">
          <form onSubmit={add} className="flex flex-col gap-3">
            <span className="text-lg">Add a person</span>
            <span className="text-[13px] leading-5 text-muted">
              With single sign-on configured, people can also join by signing in with their company account; they start as viewers.
            </span>
            <input className={field} type="email" required placeholder="Email" value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })} />
            <input className={field} placeholder="Name" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input className={field} type="password" required minLength={10} placeholder="Temporary password (10+ characters)"
              autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <RolePills value={form.role} onChange={(role) => setForm({ ...form, role })} />
            <span className="text-xs text-muted">{ROLES.find((r) => r.id === form.role)?.hint}</span>
            <Button variant="blue" className="mt-1">Add person</Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
