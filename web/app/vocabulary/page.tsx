"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, Entity } from "@/lib/api";
import { Button, Card, cx, Empty, ErrorNote, Icon } from "@/components/ui";

export default function VocabularyPage() {
  return <Suspense><Vocabulary /></Suspense>;
}

function Vocabulary() {
  const params = useSearchParams();
  const router = useRouter();
  const id = Number(params.get("id")) || null;
  const [q, setQ] = useState("");
  const [list, setList] = useState<{ id: number; label: string; kind: string; pack: string | null; alias_count: number }[]>([]);
  const [entity, setEntity] = useState<Entity | null>(null);
  const [newAlias, setNewAlias] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const t = setTimeout(() => api.entities(q).then(setList).catch((e) => setError(e.message)), 150);
    return () => clearTimeout(t);
  }, [q]);

  const loadEntity = useCallback(() => {
    if (id) api.entity(id).then(setEntity).catch((e) => setError(e.message));
    else setEntity(null);
  }, [id]);
  useEffect(loadEntity, [loadEntity]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!entity || !newAlias.trim()) return;
    await api.addAlias(entity.id, newAlias.trim());
    setNewAlias("");
    loadEntity();
  };

  return (
    <div className="mx-auto grid max-w-[1240px] gap-6 lg:grid-cols-[300px_1fr]">
      <div className="flex flex-col gap-4">
        <h1 className="display text-[40px] leading-[44px]">Vocabulary</h1>
        <label className="flex items-center gap-3 rounded-full bg-white px-5 py-3">
          <Icon name="search" className="text-muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a meaning or alias"
            className="flex-1 bg-transparent text-sm outline-none" aria-label="Find a meaning" />
        </label>
        <Card className="flex max-h-[70vh] flex-col gap-0.5 overflow-y-auto p-2">
          {list.map((e) => (
            <button key={e.id} onClick={() => router.replace(`/vocabulary?id=${e.id}`)}
              className={cx("flex items-center justify-between rounded-[16px] px-4 py-3 text-left text-sm",
                e.id === id ? "bg-primary text-white" : "hover:bg-surface-2")}>
              <span className="truncate">{e.label}</span>
              <span className={cx("text-xs", e.id === id ? "text-primary-soft" : "text-muted")}>{e.alias_count}</span>
            </button>
          ))}
        </Card>
      </div>

      <div className="flex flex-col gap-4">
        {error && <ErrorNote error={error} />}
        {!entity ? (
          <Card className="flex-1"><Empty title="Pick a meaning" body="Every meaning is an entity with the names people use for it. Add, scope or remove names here; every change is audited and instantly live in search." /></Card>
        ) : (
          <>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div className="flex flex-col gap-1">
                <span className="text-[13px] text-muted">{entity.kind}{entity.pack ? ` · ${entity.pack.replace("_", " ")} pack` : ""}</span>
                <span className="display text-[40px] leading-[44px]">{entity.label}</span>
              </div>
              <form onSubmit={add} className="flex items-center gap-2 rounded-full bg-white p-1.5 pl-5">
                <input value={newAlias} onChange={(e) => setNewAlias(e.target.value)} placeholder="Add a name people use"
                  className="w-48 bg-transparent text-sm outline-none" aria-label="New alias" />
                <Button variant="dark" className="py-2.5" disabled={!newAlias.trim()}>+ Add</Button>
              </form>
            </div>
            <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
              <Card className="relative min-h-[460px] overflow-hidden"><Graph entity={entity} /></Card>
              <Card className="flex flex-col gap-1 p-3">
                <div className="flex px-3 py-2 text-xs text-muted">
                  <span className="flex-1">Name</span><span className="w-24">Type</span><span className="w-28">Scope</span><span className="w-8" />
                </div>
                {entity.aliases.filter((a) => a.type !== "label").map((a) => (
                  <div key={a.id} className={cx("flex items-center rounded-[16px] px-3 py-3 text-sm", a.status === "rejected" && "text-muted line-through")}>
                    <span className="min-w-0 flex-1 truncate pr-2">{a.term}</span>
                    <span className="w-24 text-[13px] text-muted">{a.type}</span>
                    <span className={cx("w-28 truncate text-[13px]", a.scope ? "text-primary" : "text-muted")}>{a.scope ?? "All data"}</span>
                    <button aria-label={`Remove ${a.term}`} onClick={async () => { await api.removeAlias(a.id); loadEntity(); }}
                      className="flex h-8 w-8 items-center justify-center rounded-full text-muted hover:bg-surface-2 hover:text-danger">
                      <Icon name="x" size={14} />
                    </button>
                  </div>
                ))}
              </Card>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Graph({ entity }: { entity: Entity }) {
  const names = entity.aliases.filter((a) => a.type !== "label");
  const pending = entity.suggestions;
  const nodes = [
    ...names.map((a) => ({ text: a.term, kind: a.status === "rejected" ? "rejected" : a.scope ? "scoped" : "approved" })),
    ...pending.map((s) => ({ text: `${s.term} · suggested`, kind: "suggested" })),
  ].slice(0, 14);
  const W = 520, H = 460, cx0 = W / 2, cy0 = H / 2, R = 160;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-[460px] w-full" role="img" aria-label={`${entity.label} and its names`}>
      {nodes.map((n, i) => {
        const a = (i / nodes.length) * Math.PI * 2 - Math.PI / 2;
        const x = cx0 + Math.cos(a) * R * 1.05, y = cy0 + Math.sin(a) * R * 1.15;
        const stroke = n.kind === "suggested" ? "#D98A10" : n.kind === "rejected" ? "#CFCFCF" : "#0B5CFF";
        const fill = n.kind === "suggested" ? "#FFF3DE" : n.kind === "scoped" ? "#E7EEFF" : "#F4F4F4";
        const w = Math.min(220, 30 + n.text.length * 9);
        return (
          <g key={i}>
            <path d={`M${cx0} ${cy0} C${(cx0 + x) / 2} ${cy0} ${(cx0 + x) / 2} ${y} ${x} ${y}`} stroke={stroke} strokeWidth="1.5"
              fill="none" strokeDasharray={n.kind === "suggested" ? "5 5" : undefined} className="draw" />
            <rect x={x - w / 2} y={y - 22} width={w} height={44} rx={22} fill={fill} />
            <text x={x} y={y + 6} textAnchor="middle" fontSize="16" fill={n.kind === "rejected" ? "#6B6B6B" : n.kind === "suggested" ? "#B8740A" : "#161616"}>{n.text}</text>
          </g>
        );
      })}
      <circle cx={cx0} cy={cy0} r="74" fill="#0B5CFF" />
      {entity.label.split(" ").reduce<string[]>((lines, w) => {
        const last = lines[lines.length - 1];
        if (last && (last + " " + w).length <= 14) lines[lines.length - 1] = last + " " + w; else lines.push(w);
        return lines;
      }, []).slice(0, 3).map((l, i, arr) => (
        <text key={i} x={cx0} y={cy0 + 5 + (i - (arr.length - 1) / 2) * 19} textAnchor="middle" fontSize="16" fill="#fff">{l}</text>
      ))}
    </svg>
  );
}
