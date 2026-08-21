"use client";

import { useEffect, useState } from "react";

import type { ControllerState } from "@/types";

interface EmergencyStopControlProps {
  controller: ControllerState;
  disabled: boolean;
  active: boolean;
  error: string | null;
  onStop: () => void;
}

export function EmergencyStopControl({
  controller,
  disabled,
  active,
  error,
  onStop,
}: EmergencyStopControlProps) {
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    if (!armed) return;
    const timer = window.setTimeout(() => setArmed(false), 5_000);
    return () => window.clearTimeout(timer);
  }, [armed]);

  const requestStop = () => {
    if (!armed) {
      setArmed(true);
      return;
    }
    setArmed(false);
    onStop();
  };

  return (
    <section className="emergency-stop-panel panel" aria-labelledby="emergency-stop-title">
      <div>
        <p className="section-kicker">Hardware safety control</p>
        <h2 id="emergency-stop-title">Emergency STOP_ALL</h2>
        <p>
          Sends or queues the highest-priority stop command. It does not start irrigation,
          and safety remains unconfirmed until the controller reports IDLE.
        </p>
      </div>
      <div className="emergency-stop-actions">
        <span>Controller: <strong>{controller.status}</strong></span>
        <button
          type="button"
          className={`emergency-stop-button${armed ? " armed" : ""}`}
          disabled={disabled || active}
          onClick={requestStop}
        >
          {active ? "Sending STOP_ALL…" : armed ? "Confirm STOP_ALL" : "Emergency stop"}
        </button>
        {armed && <small>Click again within 5 seconds to confirm.</small>}
        {error && <small className="error-message">{error}</small>}
      </div>
    </section>
  );
}
