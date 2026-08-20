import type { SimulationScenarioSummary } from "@/types";

interface SimulationControlsProps {
  scenarios: SimulationScenarioSummary[];
  activeScenarioId: string | null;
  activeAction: string | null;
  actionError: string | null;
  disabled: boolean;
  onActivate: (scenarioId: string) => Promise<void>;
  onReset: () => Promise<void>;
}

const scenarioNumbers: Record<string, string> = {
  zone_a_critical: "01",
  rain_soon: "02",
  tds_correction: "03",
  freshwater_shortage: "04",
  sensor_offline: "05",
  legacy_ml_unavailable: "06",
};

export function SimulationControls({
  scenarios,
  activeScenarioId,
  activeAction,
  actionError,
  disabled,
  onActivate,
  onReset,
}: SimulationControlsProps) {
  return (
    <section className="simulation-controls panel" aria-labelledby="simulation-title">
      <div className="section-title-row compact-title-row">
        <div>
          <p className="section-kicker">Demo / Simulation Controls</p>
          <h2 id="simulation-title">Six judge-ready scenarios</h2>
        </div>
        <button
          className="reset-button"
          type="button"
          disabled={disabled || activeAction !== null}
          onClick={() => void onReset()}
        >
          {activeAction === "reset" ? "Resetting…" : "Reset baseline"}
        </button>
      </div>

      <div className="scenario-grid">
        {scenarios.map((scenario) => {
          const active = activeScenarioId === scenario.id;
          const loading = activeAction === scenario.id;
          return (
            <button
              type="button"
              className={`scenario-button${active ? " active" : ""}`}
              key={scenario.id}
              disabled={disabled || activeAction !== null}
              onClick={() => void onActivate(scenario.id)}
              aria-pressed={active}
            >
              <span className="scenario-number">{scenarioNumbers[scenario.id] ?? "--"}</span>
              <span className="scenario-copy">
                <strong>{loading ? "Loading…" : scenario.name}</strong>
                <small>{scenario.description}</small>
              </span>
              <span className="scenario-arrow" aria-hidden="true">→</span>
            </button>
          );
        })}
      </div>

      {scenarios.length === 0 && !actionError && (
        <p className="controls-message">Scenario list unavailable.</p>
      )}
      {actionError && <p className="controls-message error-message">{actionError}</p>}
      <p className="simulation-boundary">
        Scenario loads apply explicit prototype calibration through backend configuration APIs. They update planning state only and never send hardware commands.
      </p>
    </section>
  );
}
