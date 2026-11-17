"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { API, api, Config, KEY_STORAGE } from "@/lib/api";
import { Button, Card, ErrorNote, Icon } from "@/components/ui";

const PROVIDERS = [
  { id: "ollama", name: "Ollama Cloud", hint: "ONOMA_MODEL_PROVIDER=ollama · ONOMA_MODEL_NAME=gpt-oss:120b-cloud" },
  { id: "anthropic", name: "Claude", hint: "ONOMA_MODEL_PROVIDER=anthropic · ONOMA_MODEL_NAME=claude-sonnet-5-5" },
  { id: "gemini", name: "Gemini", hint: "ONOMA_MODEL_PROVIDER=gemini · ONOMA_MODEL_NAME=gemini-2.5-flash" },
  { id: "openai", name: "OpenAI-compatible", hint: "ONOMA_MODEL_PROVIDER=openai · ONOMA_MODEL_URL=https://…" },
];

export default function Settings() {
  const [config, setConfig] = useState<Config | null>(null);
  const [error, setError] = useState("");
  const [key, setKey] = useState("");
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);

  const load = () => api.config().then((c) => { setConfig(c); setError(""); }).catch((e) => setError(e.message));
  useEffect(() => {
    try { setKey(localStorage.getItem(KEY_STORAGE) ?? ""); } catch {}
    load();
  }, []);

  const saveKey = (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (key) localStorage.setItem(KEY_STORAGE, key);
      else localStorage.removeItem(KEY_STORAGE);
    } catch {}
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
    load();
  };

  const mcpJson = config ? JSON.stringify({ mcpServers: { onoma: config.mcp } }, null, 2) : "";
  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-6">
      <h1 className="display text-[40px] leading-[44px]">Settings</h1>
      {error && <ErrorNote error={error} />}
      <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
        <Card className="flex flex-col gap-3 p-6">
          <span className="text-[17px]">Model providers</span>
          <span className="text-[13px] leading-5 text-muted">
            Onoma searches without any model. A provider adds written reasons to alias suggestions. Nothing leaves this
            server unless you set one; personal columns are never sent.
          </span>
          {PROVIDERS.map((p) => {
            const active = config?.model.enabled && config.model.provider === p.id;
            return (
              <div key={p.id} className="flex items-center gap-4 rounded-[20px] bg-surface-2 p-4">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-ink text-sm text-white">{p.name[0]}</span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="text-[15px]">{p.name}</span>
                  <span className="truncate text-xs text-muted">{active ? `Using ${config!.model.name}` : p.hint}</span>
                </span>
                <span className={active ? "rounded-full bg-success-tint px-2.5 py-1 text-xs text-success" : "rounded-full bg-white px-2.5 py-1 text-xs text-muted"}>
                  {active ? "Connected" : "Not set"}
                </span>
              </div>
            );
          })}
          <span className="text-xs leading-5 text-muted">Set these as environment variables where <code>onoma serve</code> runs, with ONOMA_MODEL_KEY for the key.</span>
        </Card>

        <div className="flex min-w-0 flex-col gap-5">
          <div className="relative flex flex-col gap-4 overflow-hidden rounded-[28px] bg-primary p-6 text-white">
            <Image src="/3d/agent.png" alt="" width={190} height={190} className="art pointer-events-none absolute -right-6 -top-2" />
            <span className="relative self-start rounded-full border border-white/40 px-3 py-1.5 text-xs">MCP server · stdio</span>
            <span className="display relative max-w-[260px] text-[26px] leading-8">Let your agents search with the same vocabulary</span>
            <pre className="relative whitespace-pre-wrap break-all rounded-[16px] bg-black/25 p-4 text-[12px] leading-5">{mcpJson || "…"}</pre>
            <button onClick={() => { navigator.clipboard.writeText(mcpJson); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
              className="relative flex items-center gap-2 self-start rounded-full bg-white px-4 py-2.5 text-[13px] text-ink">
              <Icon name="copy" size={14} /> {copied ? "Copied" : "Copy client config"}
            </button>
            <span className="relative text-xs text-primary-soft">Agents can search and resolve; their alias proposals wait in the review queue.</span>
          </div>

          <Card className="flex flex-col gap-3 p-6">
            <span className="text-[17px]">API access</span>
            <span className="text-[13px] leading-5 text-muted">
              Engine at <code>{API}</code> · {config ? (config.auth === "open" ? "open (no key required)" : "requires an API key") : "unknown"}.
              Require keys with <code>ONOMA_API_KEYS=key1,key2</code>.
            </span>
            <form onSubmit={saveKey} className="flex items-center gap-2 rounded-full bg-surface-2 p-1.5 pl-5">
              <input value={key} onChange={(e) => setKey(e.target.value)} type="password" placeholder="API key for this browser"
                aria-label="API key" className="min-w-0 flex-1 bg-transparent text-sm outline-none" />
              <Button variant="dark" className="py-2.5">{saved ? "Saved" : "Save"}</Button>
            </form>
          </Card>
        </div>
      </div>
    </div>
  );
}
