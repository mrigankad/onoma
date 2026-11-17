"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Stats } from "@/lib/api";
import { Button, Card, ErrorNote } from "@/components/ui";

export default function Insights() {
  const [failed, setFailed] = useState<{ query: string; times: number; last_seen: string }[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const load = () => api.insights().then((r) => { setFailed(r.failed_queries); setStats(r.stats); }).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  const run = async (agent: "alias-miner" | "insights-analyst") => {
    const r = await api.runAgent(agent);
    setNote(`${agent.replace("-", " ")} created ${r.created} new suggestion${r.created === 1 ? "" : "s"}`);
    load();
  };

  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="display text-[40px] leading-[44px]">Insights</h1>
        <div className="flex gap-2">
          <Button variant="light" onClick={() => run("alias-miner")}>Run Alias Miner</Button>
          <Button variant="dark" onClick={() => run("insights-analyst")}>Run Insights Analyst</Button>
        </div>
      </div>
      {error && <ErrorNote error={error} />}
      {note && <div role="status" className="rounded-[20px] bg-primary-tint px-5 py-3.5 text-sm text-primary">{note} · <Link href="/review" className="underline">open review queue</Link></div>}
      <div className="grid gap-4 md:grid-cols-3">
        <div className="flex flex-col gap-1 rounded-[28px] bg-primary p-6 text-white">
          <span className="text-[13px] text-primary-soft">Zero-result rate</span>
          <span className="display text-[44px]">{stats?.zero_result_rate == null ? "—" : `${(stats.zero_result_rate * 100).toFixed(1)}%`}</span>
        </div>
        <Card className="flex flex-col gap-1 p-6">
          <span className="text-[13px] text-muted">Searches</span>
          <span className="display text-[44px]">{stats?.searches ?? "—"}</span>
        </Card>
        <Card className="flex flex-col gap-1 p-6">
          <span className="text-[13px] text-muted">Average latency</span>
          <span className="display text-[44px]">{stats ? `${stats.avg_latency_ms} ms` : "—"}</span>
        </Card>
      </div>
      <Card className="flex flex-col p-3">
        <div className="flex px-4 py-3 text-xs text-muted"><span className="flex-1">Searches that found nothing</span><span className="w-20">Times</span><span className="w-44">Last seen</span><span className="w-16" /></div>
        {failed.length === 0 && <p className="px-4 py-6 text-sm text-muted">No failed searches yet.</p>}
        {failed.map((f) => (
          <div key={f.query} className="flex items-center rounded-[18px] px-4 py-3.5 hover:bg-surface-2">
            <span className="flex-1 text-sm">“{f.query}”</span>
            <span className="w-20 text-sm">{f.times}</span>
            <span className="w-44 text-[13px] text-muted">{f.last_seen}</span>
            <Link href={`/search?q=${encodeURIComponent(f.query)}`} className="w-16 text-[13px] text-primary">Retry</Link>
          </div>
        ))}
      </Card>
    </div>
  );
}
