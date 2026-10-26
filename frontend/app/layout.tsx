import type { Metadata } from "next";
import Link from "next/link";
import { Nav } from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Paper Portfolio India",
  description: "AI investment intelligence POC: paper trading and portfolio tracking for Indian equities",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IN">
      <body className="min-h-screen antialiased">
        <div className="bg-warn px-4 py-1.5 text-center text-xs font-semibold text-on-warn">
          PAPER TRADING · SIMULATION — virtual money only. No real orders, no broker connection. Bundled market data is
          simulated.
        </div>
        <header className="border-b border-line bg-surface">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-3">
            <Link href="/" className="font-semibold text-ink">
              Paper Portfolio <span className="text-ink-2">· India</span>
            </Link>
            <Nav />
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-muted">
          Proof of concept. Figures are simulated and for demonstration only; nothing here is investment advice.
        </footer>
      </body>
    </html>
  );
}
