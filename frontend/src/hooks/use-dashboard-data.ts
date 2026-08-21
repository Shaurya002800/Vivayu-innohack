"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  activateSimulationScenario,
  emergencyStop,
  fetchDashboardSnapshot,
  fetchSimulationScenarios,
  resetSimulation,
} from "@/lib/api";
import type { DashboardContext, DashboardSnapshot, SimulationScenarioSummary } from "@/types";

const POLL_INTERVAL_MS = 1_000;

export function useDashboardData(context: DashboardContext = "live") {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [scenarios, setScenarios] = useState<SimulationScenarioSummary[]>([]);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const pollInFlight = useRef(false);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    if (pollInFlight.current) return;
    pollInFlight.current = true;
    try {
      const next = await fetchDashboardSnapshot(context);
      if (!mounted.current) return;
      setSnapshot(next);
      setConnectionError(null);
    } catch (error: unknown) {
      if (!mounted.current) return;
      setConnectionError(error instanceof Error ? error.message : "Backend is unavailable");
    } finally {
      pollInFlight.current = false;
      if (mounted.current) setIsInitialLoading(false);
    }
  }, [context]);

  useEffect(() => {
    mounted.current = true;
    const initialRefresh = window.setTimeout(() => void refresh(), 0);
    void fetchSimulationScenarios()
      .then((items) => {
        if (mounted.current) setScenarios(items);
      })
      .catch(() => {
        // The main connectivity state provides the visible failure treatment.
      });
    const timer = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => {
      mounted.current = false;
      window.clearTimeout(initialRefresh);
      window.clearInterval(timer);
    };
  }, [refresh]);

  const runAction = useCallback(
    async (key: string, action: () => Promise<void>) => {
      setActiveAction(key);
      setActionError(null);
      try {
        await action();
        await refresh();
        return true;
      } catch (error: unknown) {
        setActionError(error instanceof Error ? error.message : "Action failed");
        return false;
      } finally {
        setActiveAction(null);
      }
    },
    [refresh],
  );

  return {
    snapshot,
    scenarios,
    connectionError,
    actionError,
    activeAction,
    isInitialLoading,
    refresh,
    activateScenario: (scenarioId: string, configureCurrentSimulation = true) =>
      runAction(scenarioId, () =>
        activateSimulationScenario(scenarioId, configureCurrentSimulation)),
    resetScenario: () => runAction("reset", resetSimulation),
    emergencyStop: () => runAction("emergency-stop", async () => {
      await emergencyStop();
    }),
  };
}
