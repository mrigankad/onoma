// Typed client for the Onoma engine (/v1). Base URL from NEXT_PUBLIC_ONOMA_API.

export const API = process.env.NEXT_PUBLIC_ONOMA_API ?? "http://127.0.0.1:8000";

export type Why = { step: "typo" | "entity" | "alias" | "filter" | "keyword" | "sense" | "meaning"; text: string };

export type Hit = {
  record_id: number;
  dataset_id: number;
  dataset: string;
  title: string;
  fields: Record<string, string>;
  score: number;
  matched_via: null | {
    term: string; type: string; source: string; entity: string; entity_id: number; scoped: boolean;
  };
  why: Why[];
};

export type SearchResult = {
  query: string;
  total: number;
  latency_ms: number;
  hits: Hit[];
  understood: {
    entities: { id: number; label: string; typed: string; match: string; aliases: string[]; note: string | null }[];
    filters: { op: string; value: number; unit: string | null; text: string }[];
    corrections: { from: string; to: string; score: number }[];
    keywords: string[];
    did_you_mean: { term: string; meaning: string; score: number }[];
  };
};

export type Config = {
  version: string; auth: "open" | "api-key";
  model: { enabled: boolean; provider: string | null; name: string | null };
  mcp: { command: string; args: string[] }; tools: string[];
};

export type Card = {
  id: number; term: string; entity_id: number; entity: string; agent: string; confidence: number;
  scope_dataset_id: number | null; scope_name: string | null; reason: string;
  evidence: Record<string, unknown>; samples: { title: string; dataset: string; fields: Record<string, string> }[];
  fixes_failed_searches: number;
};

export type Dataset = {
  id: number; name: string; source: string; row_count: number; created_at: string;
  columns: { name: string; role: string; reason: string }[];
};

export type Entity = {
  id: number; label: string; kind: string; codes: Record<string, string>; pack: string | null;
  aliases: { id: number; term: string; type: string; source: string; status: string; scope: string | null;
             decided_by: string | null; decided_at: string | null }[];
  suggestions: { id: number; term: string; confidence: number; agent: string }[];
};

export type Stats = {
  records: number; datasets: number; entities: number; aliases: number; open_suggestions: number;
  searches: number; zero_result_rate: number | null; avg_latency_ms: number;
};

export type Pack = { id: string; name: string; description: string; license: string; entities: number; installed: boolean };

export const KEY_STORAGE = "onoma.apiKey";
export const TOKEN_STORAGE = "onoma.session";

function stored(name: string): string {
  try { return typeof window === "undefined" ? "" : localStorage.getItem(name) ?? ""; } catch { return ""; }
}

export function setSession(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_STORAGE, token);
    else localStorage.removeItem(TOKEN_STORAGE);
  } catch {}
}

export type Me = { id: number; email: string; name: string; role: "viewer" | "steward" | "admin" };
export const canDo = (me: Me | null, role: Me["role"]) =>
  !!me && ["viewer", "steward", "admin"].indexOf(me.role) >= ["viewer", "steward", "admin"].indexOf(role);

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const token = stored(TOKEN_STORAGE);
  const key = stored(KEY_STORAGE);
  const auth: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : key ? { "X-API-Key": key } : {};
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? { ...auth } : { "Content-Type": "application/json", ...auth },
    cache: "no-store",
  });
  if (res.status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    setSession(null);
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export const api = {
  me: () => call<Me>("/v1/auth/me"),
  login: (email: string, password: string) =>
    call<{ token: string; user: Me }>("/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  health: () => call<{ ok: boolean; sso: boolean; auth: string }>("/v1/health"),
  ssoStart: () => call<{ url: string }>("/v1/auth/oidc/start"),
  ssoFinish: (code: string, state: string) =>
    call<{ token: string; user: Me }>("/v1/auth/oidc/callback", { method: "POST", body: JSON.stringify({ code, state }) }),
  users: () => call<(Me & { created_at: string })[]>("/v1/users"),
  addUser: (u: { email: string; name: string; password: string; role: Me["role"] }) =>
    call<Me>("/v1/users", { method: "POST", body: JSON.stringify(u) }),
  setRole: (id: number, role: Me["role"]) =>
    call("/v1/users/" + id, { method: "PATCH", body: JSON.stringify({ role }) }),
  logout: () => call("/v1/auth/logout", { method: "POST" }),
  stats: () => call<Stats>("/v1/stats"),
  config: () => call<Config>("/v1/config"),
  search: (query: string, datasets?: number[]) =>
    call<SearchResult>("/v1/search", { method: "POST", body: JSON.stringify({ query, datasets, limit: 30 }) }),
  suggestions: () => call<Card[]>("/v1/suggestions"),
  decide: (id: number, decision: "same" | "different" | "scope") =>
    call(`/v1/suggestions/${id}/decision`, { method: "POST", body: JSON.stringify({ decision }) }),
  datasets: () => call<Dataset[]>("/v1/datasets"),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<(Dataset & { added: number; suggestions_created: number })[]>("/v1/datasets", { method: "POST", body: form });
  },
  entities: (q = "") => call<{ id: number; label: string; kind: string; pack: string | null; alias_count: number }[]>(
    `/v1/entities?q=${encodeURIComponent(q)}`),
  entity: (id: number) => call<Entity>(`/v1/entities/${id}`),
  addAlias: (id: number, term: string) =>
    call(`/v1/entities/${id}/aliases`, { method: "POST", body: JSON.stringify({ term }) }),
  removeAlias: (id: number) => call(`/v1/aliases/${id}`, { method: "DELETE" }),
  insights: () => call<{ failed_queries: { query: string; times: number; last_seen: string }[]; stats: Stats }>("/v1/insights"),
  runAgent: (agent: "alias-miner" | "insights-analyst") => call<{ created: number }>(`/v1/agents/${agent}/run`, { method: "POST" }),
  packs: () => call<Pack[]>("/v1/packs"),
  exportVocab: () => call<{ name: string; entities: unknown[] }>("/v1/vocabulary/export"),
  importVocab: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<{ entities: number }>("/v1/vocabulary/import", { method: "POST", body: form });
  },
  installPack: (id: string) => call<{ entities: number }>(`/v1/packs/${id}/install`, { method: "POST" }),
};
