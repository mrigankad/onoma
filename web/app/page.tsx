"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, Dataset, Stats } from "@/lib/api";
import { Button, Card, ErrorNote, Icon } from "@/components/ui";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export default function Home() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [stats, setStats] = useState<Stats | null>(null);
  const [failed, setFailed] = useState<{ query: string; times: number }[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.insights(), api.datasets()])
      .then(([ins, ds]) => {
        setStats(ins.stats);
        setFailed(ins.failed_queries.slice(0, 5));
        setDatasets(ds);
      })
      .catch((e) => setError(e.message));
  }, []);

  const go = (e: React.FormEvent) => {
    e.preventDefault();
    if (q.trim()) router.push(`/search?q=${encodeURIComponent(q.trim())}`);
  };

  const zero = stats?.zero_result_rate;
  return (
    <div className="mx-auto flex max-w-[1200px] flex-col gap-8">
      <h1 className="display text-4xl md:text-[44px]">{greeting()}</h1>
      <form onSubmit={go} className="flex items-center gap-3 rounded-full bg-white px-5 py-4" role="search">
        <Icon name="search" size={18} className="text-muted" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Search"
          placeholder={`Search ${datasets.length || ""} sources in your own words · try “heart attack in patients over 60”`}
          className="flex-1 bg-transparent text-[17px] outline-none placeholder:text-muted"
        />
        <kbd className="hidden rounded-md border border-line px-2 py-0.5 text-xs text-muted md:inline">Enter</kbd>
      </form>
      {error && <ErrorNote error={error} />}

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="flex flex-col gap-3 p-6">
          <span className="text-[13px] text-muted">Searches that found nothing</span>
          <span className="display text-[40px] leading-none">{zero == null ? "—" : `${(zero * 100).toFixed(1)}%`}</span>
          <span className="text-xs leading-5 text-muted">
            {stats ? `${stats.searches} searches so far · avg ${stats.avg_latency_ms} ms` : "No searches yet"}
          </span>
        </Card>
        <Card className="flex flex-col gap-3 p-6">
          <span className="text-[13px] text-muted">Vocabulary</span>
          <span className="display text-[40px] leading-none">{stats?.aliases ?? "—"}</span>
          <span className="text-xs leading-5 text-muted">
            approved aliases across {stats?.entities ?? 0} meanings · {stats?.records ?? 0} rows indexed
          </span>
        </Card>
        <div className="relative flex flex-col gap-3 overflow-hidden rounded-[28px] bg-attention-tint p-6">
          <Image src="/3d/review.png" alt="" width={140} height={140} className="art pointer-events-none absolute -right-2 bottom-2" />
          <span className="text-[13px] text-attention">Waiting for review</span>
          <span className="display text-[40px] leading-none">{stats?.open_suggestions ?? "—"}</span>
          <span className="max-w-[60%] text-xs leading-5 text-attention">Aliases the agents found. Only people approve them.</span>
          <Link href="/review" className="relative mt-auto self-start rounded-full bg-primary px-4 py-2.5 text-[13px] text-white">
            Start review
          </Link>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-[1.5fr_1fr]">
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-line px-6 py-4">
            <span className="text-[15px] font-medium">Searches that found nothing</span>
            <Link href="/insights" className="text-[13px] text-primary">Open insights</Link>
          </div>
          {failed.length === 0 ? (
            <p className="px-6 py-8 text-sm text-muted">Nothing failed yet. Failed searches appear here and turn into alias suggestions.</p>
          ) : (
            failed.map((f) => (
              <div key={f.query} className="flex items-center border-b border-line px-6 py-3.5 last:border-0">
                <span className="flex-1 text-sm">“{f.query}”</span>
                <span className="w-14 text-[13px] text-muted">{f.times}×</span>
                <Link href={`/search?q=${encodeURIComponent(f.query)}`} className="text-[13px] text-primary">Retry</Link>
              </div>
            ))
          )}
        </Card>
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-line px-6 py-4">
            <span className="text-[15px] font-medium">Sources</span>
            <Link href="/data" className="text-[13px] text-primary">+ Connect</Link>
          </div>
          {datasets.length === 0 ? (
            <div className="flex flex-col items-start gap-3 px-6 py-8">
              <p className="text-sm text-muted">No data yet. Upload a spreadsheet, or load the demo with <code>onoma demo</code>.</p>
              <Button variant="dark" onClick={() => router.push("/data")}>Connect data</Button>
            </div>
          ) : (
            datasets.map((d) => (
              <div key={d.id} className="flex items-center gap-3 border-b border-line px-6 py-3.5 last:border-0">
                <span className="h-2 w-2 rounded-full bg-[#4ade80]" aria-hidden />
                <span className="flex-1 text-sm">{d.name}</span>
                <span className="text-[13px] text-muted">{d.row_count.toLocaleString()} rows</span>
              </div>
            ))
          )}
        </Card>
      </div>
    </div>
  );
}
