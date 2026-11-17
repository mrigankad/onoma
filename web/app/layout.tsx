import type { Metadata } from "next";
import { Lexend } from "next/font/google";
import { Shell } from "@/components/shell";
import "./globals.css";

const lexend = Lexend({ subsets: ["latin"], variable: "--font-lexend", weight: ["300", "400", "500", "600"] });

export const metadata: Metadata = {
  title: "Onoma",
  description: "Search by meaning, with a vocabulary people can see and fix.",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={lexend.variable}>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
