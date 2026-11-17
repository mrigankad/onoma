"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { api, Me, setSession } from "@/lib/api";
import { MeContext } from "./me";
import { cx, Icon, LogoMark } from "./ui";

const NAV = [
  { href: "/", label: "Home", icon: "home" },
  { href: "/search", label: "Search", icon: "search" },
  { href: "/vocabulary", label: "Vocabulary", icon: "graph" },
  { href: "/review", label: "Review queue", sub: true, badge: true },
  { href: "/packs", label: "Packs", sub: true },
  { href: "/data", label: "Data", icon: "data" },
  { href: "/insights", label: "Insights", icon: "chart" },
  { href: "/settings", label: "Settings", icon: "gear" },
  { href: "/users", label: "Users", sub: true },
];

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const [open, setOpen] = useState<number | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const bare = path.startsWith("/login");

  useEffect(() => {
    if (bare) return;
    api.me().then(setMe).catch(() => setMe(null));
    api.stats().then((s) => setOpen(s.open_suggestions)).catch(() => setOpen(null));
  }, [path, bare]);

  const signOut = async () => {
    await api.logout().catch(() => {});
    setSession(null);
    window.location.href = "/login";
  };

  if (bare) return <main className="min-h-screen px-4 py-6 md:px-10">{children}</main>;

  return (
    <MeContext.Provider value={me}>
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col gap-6 px-3 py-5 md:flex">
        <Link href="/" className="flex items-center gap-2.5 px-2">
          <LogoMark />
          <span className="text-[17px] tracking-tight">onoma</span>
        </Link>
        <nav className="flex flex-col gap-0.5" aria-label="Main">
          {NAV.map((n) => {
            const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "flex items-center gap-2.5 rounded-full py-2 text-sm transition-colors",
                  n.sub ? "pl-9 pr-3" : "px-3",
                  active ? "bg-pill font-medium text-white" : "text-ink hover:bg-pill-off",
                )}
              >
                {n.icon && <Icon name={n.icon} className={active ? "text-white" : "text-muted"} />}
                <span className="flex-1">{n.label}</span>
                {n.badge && open ? (
                  <span className="rounded-full bg-attention-tint px-2 py-0.5 text-xs font-semibold text-attention">{open}</span>
                ) : null}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto flex flex-col gap-3 px-3">
          {me && (
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-tint text-xs font-medium text-primary">
                {(me.name || me.email).slice(0, 2).toUpperCase()}
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-[13px]">{me.name}</span>
                <span className="text-xs text-muted">{me.role}</span>
              </span>
              {me.id > 0 && (
                <button onClick={signOut} className="text-xs text-muted hover:text-ink">Sign out</button>
              )}
            </div>
          )}
          <span className="text-xs leading-5 text-muted">Open source · Apache-2.0 · Engine v0.1</span>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 md:px-10 md:py-7">{children}</main>
      <MobileNav path={path} />
    </div>
    </MeContext.Provider>
  );
}

function MobileNav({ path }: { path: string }) {
  const items = [
    { href: "/search", label: "Search" },
    { href: "/review", label: "Review" },
    { href: "/vocabulary", label: "Vocabulary" },
  ];
  return (
    <nav className="fixed inset-x-4 bottom-4 z-20 flex justify-around rounded-full bg-ink p-2 md:hidden" aria-label="Mobile">
      {items.map((i) => (
        <Link key={i.href} href={i.href}
          className={cx("rounded-full px-4 py-2.5 text-[13px]", path.startsWith(i.href) ? "bg-white text-ink" : "text-[#bdbdbd]")}>
          {i.label}
        </Link>
      ))}
    </nav>
  );
}
