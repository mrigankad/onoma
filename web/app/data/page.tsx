"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { api, canDo, Dataset } from "@/lib/api";
import { useMe } from "@/components/me";
import { Card, cx, ErrorNote, Icon } from "@/components/ui";

const ROLE_STYLE: Record<string, string> = {
  vocabulary: "bg-primary text-white", title: "bg-surface-2 text-ink", number: "bg-surface-2 text-ink",
  text: "bg-surface-2 text-ink", personal: "bg-attention-tint text-attention", other: "bg-surface-2 text-muted",
};
const ROLE_LABEL: Record<string, string> = {
  vocabulary: "Vocabulary", title: "Title", number: "Filter · number", text: "Text · by meaning",
  personal: "Personal · skipped", other: "Ignored",
};

export default function DataPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [last, setLast] = useState<{ name: string; added: number; suggestions: number } | null>(null);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const canUpload = canDo(useMe(), "steward");

  const load = () => api.datasets().then((d) => { setDatasets(d); setSelected((s) => s ?? d[0]?.id ?? null); })
    .catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  const upload = async (file?: File) => {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.upload(file);
      const first = res[0];
      setLast({ name: first.name, added: res.reduce((n, r) => n + r.added, 0), suggestions: res.reduce((n, r) => n + (r.suggestions_created ?? 0), 0) });
      await load();
      setSelected(first.id ?? (first as unknown as { dataset_id: number }).dataset_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const ds = datasets.find((d) => d.id === selected);
  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-6">
      <div className="flex flex-col gap-2">
        <span className="text-[13px] text-muted">Data · Connect a source</span>
        <h1 className="display text-[40px] leading-[44px]">Tell Onoma what each column means</h1>
      </div>
      {error && <ErrorNote error={error} />}
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="flex flex-col gap-4">
          {canUpload && <button
            onClick={() => input.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files[0]); }}
            className={cx("flex items-center gap-4 rounded-[28px] border-2 border-dashed p-6 text-left transition-colors",
              drag ? "border-primary bg-primary-tint" : "border-line-strong bg-white hover:border-primary")}
          >
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-tint text-primary">
              <Icon name="upload" size={20} />
            </span>
            <span className="flex flex-col">
              <span className="text-[15px]">{busy ? "Reading and indexing…" : "Drop a file or click to upload"}</span>
              <span className="text-[13px] text-muted">CSV, TSV, JSON or Excel. Every sheet becomes a dataset. Contact details are detected and skipped.</span>
            </span>
          </button>}
          <input ref={input} type="file" hidden accept=".csv,.tsv,.json,.xlsx,.xlsm"
            onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />

          <div className="flex flex-wrap gap-2">
            {datasets.map((d) => (
              <button key={d.id} onClick={() => setSelected(d.id)}
                className={cx("rounded-full px-4 py-2.5 text-[13px]", d.id === selected ? "bg-pill text-white" : "bg-pill-off")}>
                {d.name} · {d.row_count}
              </button>
            ))}
          </div>

          {ds && (
            <Card className="flex flex-col p-3">
              <div className="flex items-center gap-3 px-3 pb-4 pt-2">
                <span className="flex h-11 w-11 items-center justify-center rounded-full bg-primary-tint text-primary"><Icon name="data" /></span>
                <span className="flex flex-col">
                  <span className="text-[15px]">{ds.source}</span>
                  <span className="text-xs text-muted">{ds.row_count.toLocaleString()} rows · {ds.columns.length} columns</span>
                </span>
              </div>
              <div className="flex border-t border-line px-3 py-2.5 text-xs text-muted">
                <span className="w-48">Column</span><span className="flex-1">Why</span><span className="w-44">Onoma reads it as</span>
              </div>
              {ds.columns.map((c) => (
                <div key={c.name} className="flex items-center border-t border-line px-3 py-3">
                  <span className={cx("w-48 truncate text-sm", c.role === "personal" && "text-attention")}>{c.name}</span>
                  <span className="flex-1 pr-3 text-[13px] text-muted">{c.reason}</span>
                  <span className="w-44"><span className={cx("rounded-full px-3 py-1.5 text-xs", ROLE_STYLE[c.role])}>{ROLE_LABEL[c.role] ?? c.role}</span></span>
                </div>
              ))}
            </Card>
          )}
        </div>

        <div className="flex flex-col gap-4">
          <div className="relative flex h-[250px] flex-col justify-between overflow-hidden rounded-[28px] bg-primary p-6 text-white">
            <Image src="/3d/converge.png" alt="" width={190} height={190} className="art pointer-events-none absolute -right-8 -top-2" />
            <span className="relative self-start rounded-full border border-white/40 px-3 py-1.5 text-xs">After the last import</span>
            <div className="relative flex flex-col">
              <span className="display text-[64px] leading-none">{last ? last.suggestions : "—"}</span>
              <span className="text-[15px]">alias suggestions found</span>
            </div>
            <span className="relative text-[13px] text-primary-soft">
              {last ? `${last.added} rows added to ${last.name}` : "Upload a file to see what the Alias Miner finds"}
            </span>
          </div>
          <Card className="p-5 text-[13px] leading-5 text-muted">
            Rows are hashed, so re-uploading the same file only adds what changed. Personal columns never leave this server and are not stored.
          </Card>
        </div>
      </div>
    </div>
  );
}
