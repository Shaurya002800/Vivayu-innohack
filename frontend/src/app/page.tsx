import { HealthStatus } from "@/components/health-status";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col px-6 py-10 sm:px-10">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--line)] pb-6">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.24em] text-[var(--accent)]">
            InnoHack 2.0
          </p>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">VIVAYU Aqua</h1>
          <p className="mt-2 text-[var(--muted)]">Scarcity-aware, water-quality-aware irrigation</p>
        </div>
        <span className="rounded-full border border-amber-400/40 bg-amber-300/10 px-4 py-2 text-sm font-bold text-amber-200">
          SIMULATION
        </span>
      </header>

      <section className="my-auto grid gap-6 py-14 md:grid-cols-[1.35fr_0.65fr]">
        <div className="rounded-3xl border border-[var(--line)] bg-[var(--panel)]/85 p-8 shadow-2xl shadow-black/20">
          <p className="text-sm font-semibold text-[var(--accent)]">Milestone 1</p>
          <h2 className="mt-3 max-w-2xl text-3xl font-semibold leading-tight">
            The project foundation is ready for two independent irrigation zones.
          </h2>
          <p className="mt-5 max-w-2xl leading-7 text-[var(--muted)]">
            Zone telemetry, crop logic, freshwater allocation, TDS verification, and actuation remain deliberately disabled until their milestone safety checks exist.
          </p>
        </div>

        <HealthStatus />
      </section>

      <footer className="border-t border-[var(--line)] pt-6 text-sm text-[var(--muted)]">
        Legacy Vivayu output will remain research-only and cannot directly actuate irrigation.
      </footer>
    </main>
  );
}
