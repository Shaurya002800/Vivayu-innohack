"""Run the complete reproducible Vivayu research pipeline."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPTS = [
    "clean_dataset.py",
    "explore_data.py",
    "train_threshold_baseline.py",
    "train_random_forest.py",
    "build_windows.py",
    "select_research_model.py",
    "assess_model_readiness.py",
]


def main() -> None:
    script_dir = Path(__file__).parent
    for script in SCRIPTS:
        print(f"\n=== Running {script} ===")
        subprocess.run([sys.executable, str(script_dir / script)], check=True)
    print("\nPipeline complete. Start the dashboard with: python scripts/run_dashboard.py")


if __name__ == "__main__":
    main()
