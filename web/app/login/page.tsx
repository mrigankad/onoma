"use client";

import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, setSession } from "@/lib/api";
import { Button, LogoMark } from "@/components/ui";

export default function LoginPage() {
  return <Suspense><Login /></Suspense>;
}

function Login() {
  const router = useRouter();
  const next = useSearchParams().get("next") || "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sso, setSso] = useState(false);
  useEffect(() => { api.health().then((h) => setSso(h.sso)).catch(() => {}); }, []);

  const startSso = async () => {
    try {
      try { sessionStorage.setItem("onoma.next", next); } catch {}
      window.location.href = (await api.ssoStart()).url;
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api.login(email, password);
      setSession(res.token);
      router.replace(next.startsWith("/") && !next.startsWith("//") ? next : "/");
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto grid min-h-[80vh] max-w-[1000px] items-center gap-6 md:grid-cols-2">
      <div className="relative hidden h-[460px] flex-col justify-between overflow-hidden rounded-[28px] bg-primary p-8 text-white md:flex">
        <Image src="/3d/converge.png" alt="" width={260} height={260} className="art pointer-events-none absolute -bottom-6 -right-10" />
        <LogoMark size={40} inverse />
        <span className="display relative max-w-[300px] text-[34px] leading-10">Many names, one meaning.</span>
      </div>
      <form onSubmit={submit} className="flex flex-col gap-4 rounded-[28px] bg-white p-8">
        <span className="display text-[32px]">Sign in</span>
        <span className="text-sm text-muted">Your workspace admin creates accounts with <code>onoma user-add</code>.</span>
        <label className="flex flex-col gap-1.5 text-[13px] text-muted">
          Email
          <input type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)}
            className="rounded-full bg-surface-2 px-5 py-3 text-[15px] text-ink outline-none focus:ring-2 focus:ring-primary" />
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] text-muted">
          Password
          <input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)}
            className="rounded-full bg-surface-2 px-5 py-3 text-[15px] text-ink outline-none focus:ring-2 focus:ring-primary" />
        </label>
        {error && <span role="alert" className="text-sm text-danger">{error}</span>}
        <Button variant="blue" disabled={busy} className="mt-2">{busy ? "Signing in…" : "Sign in"}</Button>
        {sso && (
          <>
            <span className="flex items-center gap-3 text-xs text-muted"><span className="h-px flex-1 bg-line" />or<span className="h-px flex-1 bg-line" /></span>
            <button type="button" onClick={startSso} className="rounded-full bg-surface-2 px-5 py-3 text-sm hover:bg-pill-off">
              Continue with your company account
            </button>
          </>
        )}
      </form>
    </div>
  );
}
