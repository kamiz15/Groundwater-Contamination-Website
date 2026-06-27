"""Capture real MODFLOW plume lengths for the Orlando reference inputs.

Run inside the container (which has flopy + mf6):
    docker compose exec flask python scripts/repin_numerical.py

Paste the printed numbers into the `# TODO` asserts in
tests/test_numerical_models.py (or just confirm the model runs end-to-end).
"""
import sys
from pathlib import Path

# Make the repo root importable no matter where this script is launched from.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from numerical_models import run_numerical_model, run_numerical_model_horizontal

FIX = ROOT / "tests/fixtures/orlando_reference"


def main() -> None:
    h = pd.read_csv(FIX / "input_horizontal_W.csv", delimiter=";", decimal=".").iloc[0]
    rh = run_numerical_model_horizontal(
        source_thickness=float(h["source_thickness"]),
        grid_size=float(h["grid_size"]),
        al=float(h["al"]), at=float(h["at"]),
        gamma=float(h["gamma"]), cd=float(h["Cd"]), ca=float(h["Ca"]),
    )
    print("HORIZONTAL  "
          f"plume_length={rh.plume_length:.4f}  L_D={rh.domain_length:.2f}  "
          f"width={rh.domain_width:.2f}  Pe={rh.peclet:.2f}  perlen={rh.perlen:.0f}")

    v = pd.read_csv(FIX / "input_vertical_W.csv", delimiter=";", decimal=".").iloc[0]
    rv = run_numerical_model(
        Lz=float(v["Lz"]), grid_size=float(v["grid_size"]),
        al=float(v["al"]), atv=float(v["atv"]),
        gamma=float(v["gamma"]), cd=float(v["Cd"]), ca=float(v["Ca"]),
    )
    print("VERTICAL    "
          f"plume_length={rv.plume_length:.4f}  L_D={rv.domain_length:.2f}  "
          f"thickness={rv.aquifer_thickness:.2f}  Pe={rv.peclet:.2f}  perlen={rv.perlen:.0f}")


if __name__ == "__main__":
    main()
