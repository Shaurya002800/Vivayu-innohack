"use client";

import { useEffect, useState } from "react";

import type { HealthResponse } from "@/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function HealthStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    const controller = new AbortController();

    fetch(`${API_BASE_URL}/api/v1/health`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Backend health check failed");
        return response.json() as Promise<HealthResponse>;
      })
      .then((result) => setHealth(result))
      .catch((error: unknown) => {
        if (error instanceof Error && error.name !== "AbortError") setUnavailable(true);
      });

    return () => controller.abort();
  }, []);

  return (
    <aside className="rounded-3xl border border-[var(--line)] bg-black/20 p-7">
      <p className="text-xs font-bold uppercase tracking-[0.2em] text-[var(--muted)]">System check</p>
      <div className="mt-5 flex items-center gap-3">
        <span className={`h-3 w-3 rounded-full ${health ? "bg-emerald-400" : unavailable ? "bg-rose-400" : "animate-pulse bg-amber-300"}`} />
        <strong>{health ? "Backend connected" : unavailable ? "Backend unavailable" : "Checking backend"}</strong>
      </div>
      <dl className="mt-8 space-y-4 text-sm">
        <div className="flex justify-between gap-4 border-t border-[var(--line)] pt-4">
          <dt className="text-[var(--muted)]">Data mode</dt>
          <dd className="font-semibold uppercase">{health?.data_mode ?? "simulation"}</dd>
        </div>
        <div className="flex justify-between gap-4 border-t border-[var(--line)] pt-4">
          <dt className="text-[var(--muted)]">Schema</dt>
          <dd className="font-semibold">{health?.schema_version ?? "1.0"}</dd>
        </div>
      </dl>
    </aside>
  );
}
