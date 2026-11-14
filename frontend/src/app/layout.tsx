import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import { ShieldCheck, Trophy, Compass, Activity } from "lucide-react";

export const metadata: Metadata = {
  title: "Machiavelli | Goal-Conditioned Autonomous Chess Intelligence",
  description:
    "Autonomous goal-conditioned adversarial chess agent powered by Stockfish 19 and Lexicographical Goal Search.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#080c14] text-slate-100 min-h-screen flex flex-col selection:bg-amber-500/30 selection:text-amber-200">
        {/* Top Navbar */}
        <header className="border-b border-slate-800/80 bg-slate-950/70 backdrop-blur-md sticky top-0 z-50 px-4 lg:px-8 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/" className="flex items-center gap-2 group">
              <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-amber-500 via-amber-600 to-amber-800 flex items-center justify-center shadow-lg shadow-amber-500/20 group-hover:scale-105 transition-transform duration-200">
                <span className="font-serif font-black text-slate-950 text-xl">M</span>
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-bold tracking-wider text-base text-slate-100 group-hover:text-amber-400 transition-colors">
                    MACHIAVELLI
                  </span>
                  <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 font-semibold">
                    Core v1.0
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 font-mono hidden sm:block">
                  Adversarial Goal-Conditioned Chess Engine
                </p>
              </div>
            </Link>
          </div>

          <nav className="flex items-center gap-1 sm:gap-2">
            <Link
              href="/"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors"
            >
              <Compass className="w-4 h-4 text-amber-400" />
              <span>Mission Control</span>
            </Link>
            <Link
              href="/benchmark"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors"
            >
              <Trophy className="w-4 h-4 text-amber-400" />
              <span>Benchmark Tournament</span>
            </Link>
          </nav>
        </header>

        {/* Main Content Area */}
        <main className="flex-1 w-full max-w-[1720px] mx-auto p-3 lg:p-6 flex flex-col gap-6">
          {children}
        </main>

        {/* Footer */}
        <footer className="border-t border-slate-900 bg-slate-950/60 text-slate-400 text-xs px-6 py-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Formal Mathematical Invariant Proof Engine & Lexicographic Search</span>
          </div>
          <div className="flex items-center gap-4 text-slate-400 font-mono text-[11px]">
            <span>Tactics: Stockfish 19 UCI</span>
            <span>Opponent Modeling: Adversarial</span>
            <span>Lineage: Persistent IDs</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
