"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, Dataset, Hit, SearchResult } from "@/lib/api";
import { Card, cx, Empty, ErrorNote, Icon, Pill, RoundIcon } from "@/components/ui";

const ART: Record<string, string> = {
  condition: "/3d/heart.png", symptom: "/3d/heart.png", drug: "/3d/heart.png",
  chemical: "/3d/flange.png", material: "/3d/flange.png", size: "/3d/flange.png", part: "/3d/flange.png",
};

function iconFor(dataset: string) {
  const d = dataset.toLowerCase();
  if (d.includes("clinical") || d.includes("note")) return "doc";
  if (d.includes("part") || d.includes("stock")) return "layers";
  return "pulse";
}

export default function SearchPage() {
  return (
    <Suspense>
      <SearchView />
    </Suspense>
  );
}

function SearchView() {
  const params = useSearchParams();
  const router = useRouter();
  const initial = params.get("q") ?? "";
  const [q, setQ] = useState(initial);
  const [res, setRes] = useState<SearchResult | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [scope, setScope] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [kinds, setKinds] = useState<Record<number, string>>({});

  useEffect(() => { api.datasets().then(setDatasets).catch(() => {}); }, []);

  const run = useCallback(async (query: string, ds: number | null) => {
    if (!query.trim()) { setRes(null); return; }
    setLoading(true);
    setError("");
    try {
      const r = await api.search(query, ds ? [ds] : undefined);
      setRes(r);
      const ids = r.understood.entities.map((e) => e.id).filter((id) => !(id in kinds));
      const fetched = await Promise.all(ids.map((id) => api.entity(id).catch(() => null)));
      setKinds((k) => ({ ...k, ...Object.fromEntries(fetched.filter(Boolean).map((e) => [e!.id, e!.kind])) }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [kinds]);

  useEffect(() => {
    run(initial, scope);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial, scope]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    router.replace(`/search?q=${encodeURIComponent(q.trim())}`);
  };

  const main = res?.understood.entities[0];
  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-6">
      <div className="flex flex-wrap items-center gap-2">
        <form onSubmit={submit} role="search" className="flex min-w-[280px] flex-1 items-center gap-3 rounded-full bg-white px-5 py-3.5">
          <Icon name="search" size={18} />
          <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search" autoFocus
            placeholder="Search in your own words" className="flex-1 bg-transparent text-base outline-none placeholder:text-muted" />
          {res && <span className="hidden text-[13px] text-muted sm:inline">{res.total} results · {res.latency_ms} ms</span>}
        </form>
        <Pill active={scope === null} onClick={() => setScope(null)}>All sources</Pill>
        {datasets.map((d) => (
          <Pill key={d.id} active={scope === d.id} onClick={() => setScope(d.id)}>{d.name}</Pill>
        ))}
      </div>

      {error && <ErrorNote error={error} />}
      {!res && !loading && !error && (
        <Card><Empty title="Ask in your own words" body="Onoma expands your words through the shared vocabulary, filters numbers like “over 60” or “under 40%”, and shows why every row matched." /></Card>
      )}
      {res && res.total === 0 && (
        <Card>
          <Empty title="Nothing found yet"
            body={res.understood.entities.length
              ? "The meaning was understood, but no row matches it with these filters. Try removing a filter."
              : "No known meaning for these words. This search is logged; the Insights Analyst will propose an alias that would have found results."}
            action={
              <div className="flex flex-wrap justify-center gap-2">
                {res.understood.did_you_mean.map((d) => (
                  <Link key={d.term} href={`/search?q=${encodeURIComponent(d.term)}`}
                    className="rounded-full bg-primary-tint px-4 py-2 text-[13px] text-primary">
                    Did you mean “{d.term}”? <span className="text-muted">· {d.meaning}</span>
                  </Link>
                ))}
                <Link href="/insights" className="px-4 py-2 text-[13px] text-muted">See failed searches</Link>
              </div>
            } />
        </Card>
      )}
      {res && res.total > 0 && <ResultsWithLines res={res} kind={main ? kinds[main.id] : undefined} />}
    </div>
  );
}

function ResultsWithLines({ res, kind }: { res: SearchResult; kind?: string }) {
  const wrap = useRef<HTMLDivElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const rows = useRef<(HTMLDivElement | null)[]>([]);
  const [lines, setLines] = useState<{ d: string; tone: string }[]>([]);
  const [height, setHeight] = useState(0);
  const [open, setOpen] = useState<number | null>(0);
  const main = res.understood.entities[0];

  const measure = useCallback(() => {
    if (!wrap.current || !card.current) return;
    const box = wrap.current.getBoundingClientRect();
    const c = card.current.getBoundingClientRect();
    const sy = c.top + c.height / 2 - box.top;
    const out = rows.current.slice(0, res.hits.length).map((r, i) => {
      if (!r) return null;
      const rb = r.getBoundingClientRect();
      const ty = rb.top + (rb.height > 120 ? 44 : rb.height / 2) - box.top;
      const h = res.hits[i];
      const tone = !h.matched_via ? "#CFCFCF" : h.matched_via.type === "exact words" ? "#9DB9FF" : "#0B5CFF";
      return { d: `M0 ${sy} C70 ${sy} 70 ${ty} 140 ${ty}`, tone };
    });
    setLines(out.filter(Boolean) as { d: string; tone: string }[]);
    setHeight(box.height);
  }, [res]);

  useLayoutEffect(() => {
    measure();
    const ro = new ResizeObserver(measure);
    if (wrap.current) ro.observe(wrap.current);
    return () => ro.disconnect();
  }, [measure, open]);

  return (
    <div ref={wrap} className="relative grid gap-6 lg:grid-cols-[330px_140px_1fr] lg:gap-0">
      <div className="flex flex-col gap-3.5">
        <h2 className="display text-[40px] leading-[44px]">{main ? "Understood as" : "Keyword match"}</h2>
        {main ? (
          <div ref={card} className="rise relative flex h-[230px] flex-col justify-between overflow-hidden rounded-[28px] bg-primary p-6 text-white">
            {ART[kind ?? ""] && (
              <Image src={ART[kind!]} alt="" width={150} height={150} className="art pointer-events-none absolute -bottom-3 -right-3" />
            )}
            <div className="relative flex items-start justify-between">
              <span className="rounded-full border border-white/40 px-3 py-1.5 text-xs">entity · {main.aliases.length} names</span>
              <Link href={`/vocabulary?id=${main.id}`} aria-label={`Open ${main.label}`}
                className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-ink"><Icon name="arrow" /></Link>
            </div>
            <span className="display relative max-w-[190px] text-[28px] leading-8">{main.label}</span>
            <span className="relative max-w-[175px] self-start truncate rounded-full bg-white/20 px-3.5 py-2 text-[13px]">you typed “{main.typed}”</span>
          </div>
        ) : (
          <div ref={card} className="rounded-[28px] bg-white p-6 text-sm leading-6 text-muted">
            No vocabulary meaning for these words, so this is a plain keyword search on: {res.understood.keywords.join(", ")}.
          </div>
        )}
        {main && (
          <div className="flex flex-wrap gap-2">
            {main.aliases.map((a) => (
              <span key={a} className={cx("rounded-full px-3.5 py-2 text-[13px]",
                a.toLowerCase() === main.typed ? "bg-primary-tint text-primary" : "bg-white")}>{a}</span>
            ))}
          </div>
        )}
        {res.understood.entities.slice(1).map((e) => (
          <div key={e.id} className="rounded-[20px] bg-white px-5 py-3.5 text-sm">
            <span className="text-muted">and “{e.typed}” as </span>{e.label}
          </div>
        ))}
        {(res.understood.filters.length > 0 || res.understood.corrections.length > 0 || main?.note) && (
          <div className="flex flex-col gap-1.5 rounded-[24px] bg-white px-5 py-4 text-sm">
            <span className="text-xs text-muted">Also applied</span>
            {res.understood.corrections.map((c) => <span key={c.from}>spelling: “{c.from}” → “{c.to}”</span>)}
            {res.understood.filters.map((f) => <span key={f.text}>filter: {f.op === ">" ? "more than" : "less than"} {f.value}{f.unit === "%" ? "%" : ""} · from “{f.text}”</span>)}
            {main?.note && <span className="text-attention">{main.note}</span>}
          </div>
        )}
      </div>

      <svg className="pointer-events-none hidden overflow-visible lg:block" width="140" height={height} aria-hidden>
        {lines.map((l, i) => (
          <path key={i} d={l.d} stroke={l.tone} strokeWidth="1.5" fill="none" className="draw" style={{ animationDelay: `${i * 40}ms` }} />
        ))}
      </svg>

      <Card className="flex flex-col p-2">
        <div className="flex items-center justify-between px-5 pb-3 pt-4">
          <span className="text-[15px] font-medium">Top results</span>
          <span className="text-[13px] text-muted">{res.total} found</span>
        </div>
        {res.hits.map((h, i) => (
          <ResultRow key={h.record_id} hit={h} open={open === i} onToggle={() => setOpen(open === i ? null : i)}
            refFn={(el) => { rows.current[i] = el; }} />
        ))}
      </Card>
    </div>
  );
}

function ResultRow({ hit, open, onToggle, refFn }:
  { hit: Hit; open: boolean; onToggle: () => void; refFn: (el: HTMLDivElement | null) => void }) {
  const via = hit.matched_via;
  const meaning = via && via.type !== "exact words";
  return (
    <div ref={refFn} className={cx("rise rounded-[20px] transition-colors", open && "bg-surface-2")}>
      <button onClick={onToggle} aria-expanded={open}
        className="flex min-h-[88px] w-full items-center gap-3.5 rounded-[20px] px-5 py-3 text-left">
        <RoundIcon name={iconFor(hit.dataset)} tone={via ? "blue" : "light"} />
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="truncate text-base">{hit.title}</span>
          <span className="text-[13px] text-muted">
            {hit.dataset}
            {via && <> · {meaning ? <>matched via <span className="text-primary">{via.term}</span></> : "exact words"}</>}
          </span>
        </span>
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white">
          <Icon name="arrow" className={cx("transition-transform", open && "rotate-90")} />
        </span>
      </button>
      {open && (
        <div className="flex flex-col gap-3 px-5 pb-5 pl-[86px]">
          <ol className="flex flex-col gap-1.5" aria-label="Why this matched">
            {hit.why.map((w, i) => (
              <li key={i} className="flex gap-2 text-[13px] leading-5">
                <span className={cx("mt-1.5 h-2 w-2 shrink-0 rounded-full",
                  w.step === "alias" ? "bg-primary" : w.step === "filter" ? "bg-attention" : w.step === "meaning" ? "bg-[#9DB9FF]" : "bg-ink")} />
                {w.text}
              </li>
            ))}
          </ol>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[13px]">
            {Object.entries(hit.fields).map(([k, v]) => (
              <div key={k} className="contents"><dt className="text-muted">{k}</dt><dd>{String(v)}</dd></div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}
