"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { api, setSession } from "@/lib/api";
import { LogoMark } from "@/components/ui";

export default function CallbackPage() {
  return <Suspense><Callback /></Suspense>;
}

function Callback() {
  const params = useSearchParams();
  const [error, setError] = useState("");
  const once = useRef(false);

  useEffect(() => {
    if (once.current) return;
    once.current = true;
    const code = params.get("code");
    const state = params.get("state");
    if (!code || !state) {
      setError(params.get("error_description") || "The identity provider did not return a sign-in code.");
      return;
    }
    api.ssoFinish(code, state)
      .then((res) => {
        setSession(res.token);
        let next = "/";
        try { next = sessionStorage.getItem("onoma.next") || "/"; sessionStorage.removeItem("onoma.next"); } catch {}
        window.location.replace(next.startsWith("/") && !next.startsWith("//") ? next : "/");
      })
      .catch((e) => setError((e as Error).message));
  }, [params]);

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-[420px] flex-col items-center justify-center gap-5 text-center">
      <LogoMark size={44} />
      {error ? (
        <>
          <span className="display text-[28px]">Sign-in didn’t finish</span>
          <span role="alert" className="text-sm text-muted">{error}</span>
          <Link href="/login" className="rounded-full bg-ink px-5 py-3 text-sm text-white">Back to sign in</Link>
        </>
      ) : (
        <span className="display text-[28px]">Signing you in…</span>
      )}
    </div>
  );
}
