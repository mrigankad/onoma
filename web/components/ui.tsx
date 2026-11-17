"use client";

import { ButtonHTMLAttributes, ReactNode } from "react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export function LogoMark({ size = 28, inverse = false }: { size?: number; inverse?: boolean }) {
  const bg = inverse ? "#FFFFFF" : "#0B5CFF";
  const fg = inverse ? "#0B5CFF" : "#FFFFFF";
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" aria-hidden>
      <rect width="120" height="120" rx="34" fill={bg} />
      <path d="M30 34 C58 34 58 60 84 60M30 60 L84 60M30 86 C58 86 58 60 84 60" stroke={fg} strokeWidth="8" fill="none" strokeLinecap="round" />
      <circle cx="30" cy="34" r="9" fill={fg} /><circle cx="30" cy="60" r="9" fill={fg} />
      <circle cx="30" cy="86" r="9" fill={fg} /><circle cx="86" cy="60" r="17" fill={fg} />
    </svg>
  );
}

const paths: Record<string, ReactNode> = {
  home: <path d="M3 11l9-7 9 7v9a1 1 0 01-1 1h-5v-6H9v6H4a1 1 0 01-1-1z" />,
  search: <><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></>,
  graph: <><circle cx="6" cy="12" r="3" /><circle cx="18" cy="6" r="3" /><circle cx="18" cy="18" r="3" /><path d="M9 11l6-4M9 13l6 4" /></>,
  data: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></>,
  chart: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  layers: <path d="M4 7l8-4 8 4-8 4zM4 12l8 4 8-4M4 17l8 4 8-4" />,
  check: <path d="M5 12l5 5 9-10" />,
  x: <path d="M6 6l12 12M18 6L6 18" />,
  scope: <><rect x="4" y="4" width="16" height="16" rx="4" /><path d="M9 12h6" /></>,
  arrow: <path d="M7 17L17 7M9 7h8v8" />,
  plus: <path d="M12 5v14M5 12h14" />,
  upload: <path d="M12 16V4M7 9l5-5 5 5M4 20h16" />,
  pulse: <path d="M3 12h4l2-5 4 10 2-5h6" />,
  doc: <path d="M7 3h8l4 4v14H7zM11 12h6M11 16h6" />,
  gear: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" /></>,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a1 1 0 00-1-1H5a1 1 0 00-1 1v10a1 1 0 001 1h3" /></>,
  spark: <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6" />,
};

export function Icon({ name, size = 16, className, stroke = "currentColor", width = 2 }:
  { name: keyof typeof paths | string; size?: number; className?: string; stroke?: string; width?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth={width}
      strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      {paths[name]}
    </svg>
  );
}

export function Pill({ active, children, className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  return (
    <button
      {...rest}
      className={cx(
        "rounded-full px-4 py-2.5 text-[13px] transition-colors disabled:opacity-40",
        active ? "bg-pill text-white" : "bg-pill-off text-ink hover:bg-line-strong",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Button({ variant = "dark", className, children, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "dark" | "blue" | "light" | "ghost" }) {
  const styles = {
    dark: "bg-ink text-white hover:bg-black",
    blue: "bg-primary text-white hover:bg-[#0047d6]",
    light: "bg-white text-ink hover:bg-surface-2",
    ghost: "bg-surface-2 text-ink hover:bg-pill-off",
  }[variant];
  return (
    <button {...rest} className={cx("rounded-full px-5 py-3 text-sm transition-colors disabled:opacity-40", styles, className)}>
      {children}
    </button>
  );
}

export function RoundIcon({ name, tone = "blue", size = 52 }: { name: string; tone?: "blue" | "light" | "dark" | "amber"; size?: number }) {
  const t = {
    blue: "bg-primary text-white", light: "bg-surface-2 text-ink", dark: "bg-ink text-white",
    amber: "border-[1.5px] border-dashed border-attention text-attention",
  }[tone];
  return (
    <span className={cx("inline-flex shrink-0 items-center justify-center rounded-full", t)} style={{ width: size, height: size }}>
      <Icon name={name} size={Math.round(size * 0.38)} />
    </span>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cx("rounded-[28px] bg-surface", className)}>{children}</div>;
}

export function Empty({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
      <span className="display text-3xl">{title}</span>
      <span className="max-w-md text-sm leading-6 text-muted">{body}</span>
      {action}
    </div>
  );
}

export function ErrorNote({ error }: { error: string }) {
  return (
    <div role="alert" className="rounded-[20px] bg-attention-tint px-5 py-4 text-sm text-attention">
      <b className="font-medium">Can’t reach the Onoma engine.</b> {error}. Start it with <code>onoma serve</code>.
    </div>
  );
}
