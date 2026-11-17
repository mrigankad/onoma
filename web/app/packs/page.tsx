"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { api, canDo, Pack } from "@/lib/api";
import { useMe } from "@/components/me";
import { Card, ErrorNote, Icon } from "@/components/ui";

const ART: Record<string, string> = {
  retail: "/3d/pack-retail.png", healthcare: "/3d/pack-healthcare.png",
  tech_skills: "/3d/pack-tech.png", industrial: "/3d/pack-industrial.png",
};

export default function Packs() {
  const [packs, setPacks] = useState<Pack[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const isAdmin = canDo(useMe(), "admin");

  const exportVocab = async () => {
    const data = await api.exportVocab();
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 1)], { type: "application/json" }));
    const link = Object.assign(document.createElement("a"), { href: url, download: "onoma-vocabulary.json" });
    link.click();
    URL.revokeObjectURL(url);
    setNote(`Exported ${data.entities.length} meanings with your team’s own names.`);
  };
  const importVocab = async (f?: File) => {
    if (!f) return;
    try {
      const r = await api.importVocab(f);
      setNote(`Imported ${r.entities} meanings.`);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const load = () => api.packs().then(setPacks).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-6">
      <div className="flex flex-col gap-2">
        <span className="text-[13px] text-muted">Vocabulary · Packs</span>
        <h1 className="display text-[40px] leading-[44px]">Start with words someone already mapped</h1>
      </div>
      {error && <ErrorNote error={error} />}
      <Card className="flex flex-wrap items-center gap-4 p-4 pl-6">
        <span className="flex-1 text-sm">
          Share your vocabulary: export the names your team approved as a pack, or install a pack someone shared.
        </span>
        <button onClick={exportVocab} className="rounded-full bg-surface-2 px-4 py-2.5 text-[13px] hover:bg-pill-off">Export as pack</button>
        {isAdmin && <button onClick={() => file.current?.click()} className="rounded-full bg-ink px-4 py-2.5 text-[13px] text-white">Import a pack</button>}
        <input ref={file} type="file" accept=".json" hidden onChange={(e) => { importVocab(e.target.files?.[0]); e.target.value = ""; }} />
      </Card>
      {note && <div role="status" className="rounded-[20px] bg-primary-tint px-5 py-3.5 text-sm text-primary">{note}</div>}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {packs.map((p) => (
          <Card key={p.id} className="flex flex-col gap-3 p-3 pb-5">
            <div className="relative h-[200px] overflow-hidden rounded-[20px] bg-surface-2">
              {ART[p.id] && <Image src={ART[p.id]} alt="" fill sizes="300px" className="object-cover" />}
            </div>
            <div className="flex items-center justify-between gap-2 px-2.5">
              <span className="text-lg">{p.name}</span>
              {p.installed ? (
                <span className="shrink-0 rounded-full bg-success-tint px-2.5 py-1 text-xs text-success">Installed</span>
              ) : isAdmin && (
                <button aria-label={`Install ${p.name}`} disabled={busy === p.id}
                  onClick={async () => { setBusy(p.id); await api.installPack(p.id); setBusy(null); load(); }}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ink text-white disabled:opacity-40">
                  <Icon name="plus" />
                </button>
              )}
            </div>
            <span className="px-2.5 text-[13px] leading-5 text-muted">{p.entities} meanings · {p.license}</span>
            <span className="px-2.5 text-[13px] leading-5">{p.description}</span>
          </Card>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-4 rounded-full bg-ink px-6 py-5">
        <span className="flex-1 text-[15px] text-white">Packs stay editable: your changes override the pack and survive updates.</span>
        <span className="text-[13px] text-[#cfcfcf]">Licensed vocabularies (UMLS, CAS) are imported by you, never shipped.</span>
      </div>
    </div>
  );
}
