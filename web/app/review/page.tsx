"use client";

import { useCallback, useEffect, useState } from "react";
import { api, canDo, Card as CardT } from "@/lib/api";
import { useMe } from "@/components/me";
import { Card, cx, Empty, ErrorNote, Icon } from "@/components/ui";

type Decision = "same" | "different" | "scope";

export default function Review() {
  const [queue, setQueue] = useState<CardT[]>([]);
  const [idx, setIdx] = useState(0);
  const [done, setDone] = useState(0);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(() => {
    api.suggestions().then((q) => { setQueue(q); setIdx(0); setLoaded(true); }).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const card = queue[idx];
  const me = useMe();
  const canDecide = canDo(me, "steward");

  const decide = useCallback(async (d: Decision) => {
    if (!card || busy || !canDecide) return;
    if (d === "scope" && !card.scope_dataset_id) return;
    setBusy(true);
    try {
      await api.decide(card.id, d);
      setDone((n) => n + 1);
      const label = d === "same" ? `“${card.term}” now finds ${card.entity}` :
        d === "scope" ? `“${card.term}” = ${card.entity}, only in ${card.scope_name}` : `“${card.term}” kept separate`;
      setToast(label);
      setTimeout(() => setToast(""), 3000);
      setQueue((q) => q.filter((c) => c.id !== card.id));
      setIdx((i) => Math.max(0, Math.min(i, queue.length - 2)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [card, busy, queue.length, canDecide]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      const k = e.key.toLowerCase();
      if (k === "a") decide("same");
      if (k === "r") decide("different");
      if (k === "s") decide("scope");
      if (k === "arrowdown" || k === "j") setIdx((i) => Math.min(i + 1, queue.length - 1));
      if (k === "arrowup" || k === "k") setIdx((i) => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [decide, queue.length]);

  const total = queue.length + done;
  return (
    <div className="mx-auto grid max-w-[1240px] gap-6 lg:grid-cols-[340px_1fr]">
      <div className="flex flex-col gap-4">
        <h1 className="display text-[40px] leading-[44px]">Review queue</h1>
        {error && <ErrorNote error={error} />}
        <Card className="flex flex-col gap-1 p-2.5">
          {queue.length === 0 && loaded && <p className="p-4 text-sm text-muted">Nothing waiting.</p>}
          {queue.map((c, i) => (
            <button key={c.id} onClick={() => setIdx(i)}
              className={cx("flex items-center gap-3 rounded-[20px] p-3.5 text-left transition-colors",
                i === idx ? "bg-primary text-white" : "hover:bg-surface-2")}>
              <span className={cx("flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[13px]",
                i === idx ? "bg-white text-primary" : "bg-surface-2")}>{i + 1}</span>
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-sm">{c.term} → {c.entity}</span>
                <span className={cx("truncate text-xs", i === idx ? "text-primary-soft" : "text-muted")}>
                  {c.agent.replace("-", " ")} · {Math.round(c.confidence * 100)}%
                </span>
              </span>
            </button>
          ))}
        </Card>
        <Card className="flex flex-col gap-2 p-5">
          <div className="flex justify-between text-[13px]"><span className="text-muted">This session</span><span>{done} of {total} done</span></div>
          <div className="h-2 rounded-full bg-surface-2">
            <div className="h-2 rounded-full bg-primary transition-all" style={{ width: total ? `${(done / total) * 100}%` : 0 }} />
          </div>
        </Card>
      </div>

      <div className="flex flex-col gap-4">
        {!card ? (
          <Card className="flex-1">
            {loaded && <Empty title="All clear" body="Every suggestion has a human decision. The Alias Miner runs again after each import; the Insights Analyst runs on failed searches." />}
          </Card>
        ) : (
          <>
            <Card className="rise flex flex-1 flex-col gap-7 p-8" key={card.id}>
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-attention-tint px-3 py-1.5 text-xs text-attention">
                  Suggested by {card.agent.replace("-", " ")} · confidence {card.confidence.toFixed(2)}
                </span>
                <span className="text-[13px] text-muted">{idx + 1} of {queue.length}</span>
              </div>
              <div className="flex flex-wrap items-center gap-6">
                <span className="display rounded-full bg-surface-2 px-7 py-4 text-[40px]">{card.term}</span>
                <svg width="110" height="36" aria-hidden><path d="M0 18 C36 0 72 36 104 18" stroke="#0B5CFF" strokeWidth="2" strokeDasharray="5 5" fill="none" /><circle cx="104" cy="18" r="5" fill="#0B5CFF" /></svg>
                <span className="display rounded-full bg-primary px-7 py-4 text-[40px] text-white">{card.entity}</span>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="flex flex-col gap-2 rounded-[20px] bg-surface-2 p-5">
                  <span className="text-xs text-muted">Why we think so</span>
                  <span className="text-sm leading-6">{card.reason}</span>
                </div>
                <div className="flex flex-col gap-2 rounded-[20px] bg-surface-2 p-5">
                  <span className="text-xs text-muted">Searches it would fix</span>
                  <span className="text-sm leading-6">
                    {card.fixes_failed_searches
                      ? `${card.fixes_failed_searches} failed searches mention “${card.term}”.`
                      : `After approval, searching “${card.entity}” also finds rows that only say “${card.term}”.`}
                  </span>
                </div>
              </div>
              {card.samples.length > 0 && (
                <div className="flex flex-col">
                  <span className="pb-2 text-xs text-muted">Sample rows</span>
                  {card.samples.map((s, i) => (
                    <div key={i} className="flex flex-wrap justify-between gap-2 border-t border-line py-3 text-sm">
                      <span>{s.title}</span><span className="text-muted">{s.dataset}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
            {!canDecide && me && (
              <div className="rounded-[20px] bg-surface-2 px-5 py-3 text-center text-sm text-muted">
                You can read the queue. A steward or admin makes the decisions.
              </div>
            )}
            <div className={cx("flex flex-wrap items-center justify-center gap-5 rounded-full bg-white p-4", !canDecide && "pointer-events-none opacity-40")}>
              <Choice label="Same thing" k="A" icon="check" tone="dark" onClick={() => decide("same")} disabled={busy} />
              <span className="h-8 w-px bg-line" aria-hidden />
              <Choice label="Different" k="R" icon="x" tone="light" onClick={() => decide("different")} disabled={busy} />
              <span className="h-8 w-px bg-line" aria-hidden />
              <Choice label={card.scope_name ? `Only in ${card.scope_name}` : "Only in one dataset"} k="S" icon="scope" tone="tint"
                onClick={() => decide("scope")} disabled={busy || !card.scope_dataset_id} />
            </div>
          </>
        )}
      </div>
      {toast && (
        <div role="status" className="rise fixed bottom-6 left-1/2 z-30 -translate-x-1/2 rounded-full bg-[#2a2a2a] px-5 py-3 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}

function Choice({ label, k, icon, tone, onClick, disabled }:
  { label: string; k: string; icon: string; tone: "dark" | "light" | "tint"; onClick: () => void; disabled?: boolean }) {
  const t = { dark: "bg-ink text-white", light: "bg-surface-2 text-ink", tint: "bg-primary-tint text-primary" }[tone];
  return (
    <button onClick={onClick} disabled={disabled} className="flex items-center gap-2.5 rounded-full pr-3 disabled:opacity-40">
      <span className={cx("flex h-14 w-14 items-center justify-center rounded-full", t)}><Icon name={icon} size={20} width={2.5} /></span>
      <span className="text-sm">{label} <span className="text-muted">· {k}</span></span>
    </button>
  );
}
