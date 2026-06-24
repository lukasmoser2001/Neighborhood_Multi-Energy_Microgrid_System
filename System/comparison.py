"""
comparison.py — Cross-configuration comparison of annual simulation results.

Scans Results/Tables/ for all annual_results_<abbreviation>.csv files,
reads annual_cost_total_eur and annual_emissions_total_kg for each
configuration, then writes:
  - Results/Tables/system_comparison.csv   (comparison table)
  - Results/Figures/system_comparison.pdf  (grouped bar chart)

The system configuration abbreviation (e.g. pv_hpa_bess) is taken
directly from the filename and used as the legend label.
"""

from pathlib import Path
import csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
TABLES_DIR = BASE_DIR / "Results" / "Tables"
FIGURES_DIR = BASE_DIR / "Results" / "Figures"

COST_COL = "annual_cost_total_eur"
EMISSIONS_COL = "annual_emissions_total_kg"


def collect_annual_results() -> list[dict]:
    """Return a list of dicts with keys: config, cost_eur, emissions_kg."""
    records = []
    pattern = "annual_results_*.csv"
    files = sorted(TABLES_DIR.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No annual_results_*.csv files found in {TABLES_DIR}. "
            "Run main.py for each configuration first."
        )
    for path in files:
        stem = path.stem  # e.g. annual_results_pv_hpa_bess
        config_abbrev = stem[len("annual_results_"):]  # e.g. pv_hpa_bess
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cost = float(row[COST_COL]) if row.get(COST_COL) else 0.0
                emissions = float(row[EMISSIONS_COL]) if row.get(EMISSIONS_COL) else 0.0
                records.append(
                    {
                        "config": config_abbrev,
                        "annual_cost_total_eur": round(cost, 2),
                        "annual_emissions_total_kg": round(emissions, 2),
                    }
                )
    return records


def write_comparison_table(records: list[dict]) -> Path:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TABLES_DIR / "system_comparison.csv"
    fieldnames = ["config", "annual_cost_total_eur", "annual_emissions_total_kg"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"  comparison table written to: {out_path}")
    return out_path


def plot_comparison_chart(records: list[dict]) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIGURES_DIR / "system_comparison.pdf"

    configs = [r["config"] for r in records]
    costs = [r["annual_cost_total_eur"] for r in records]
    emissions = [r["annual_emissions_total_kg"] for r in records]

    x = np.arange(len(configs))
    bar_width = 0.35

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(max(10, len(configs) * 2.5), 6))

    # Cost bar chart
    bars1 = ax1.bar(x, costs, width=bar_width, color="#1f77b4", edgecolor="white", linewidth=0.6)
    ax1.set_title("Annual Total Cost")
    ax1.set_ylabel("Cost [EUR/year]")
    ax1.set_xticks(x)
    ax1.set_xticklabels(configs, rotation=30, ha="right", fontsize=9)
    ax1.bar_label(bars1, fmt="%.0f", padding=3, fontsize=8)
    ax1.grid(axis="y", linestyle="--", alpha=0.4)
    ax1.set_axisbelow(True)

    # Emissions bar chart
    bars2 = ax2.bar(x, emissions, width=bar_width, color="#2ca02c", edgecolor="white", linewidth=0.6)
    ax2.set_title("Annual Total Emissions")
    ax2.set_ylabel("Emissions [kg CO2eq/year]")
    ax2.set_xticks(x)
    ax2.set_xticklabels(configs, rotation=30, ha="right", fontsize=9)
    ax2.bar_label(bars2, fmt="%.0f", padding=3, fontsize=8)
    ax2.grid(axis="y", linestyle="--", alpha=0.4)
    ax2.set_axisbelow(True)

    fig.suptitle("System Configuration Comparison", fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    print(f"  comparison chart saved to: {out_path}")
    return out_path


def main() -> None:
    records = collect_annual_results()
    write_comparison_table(records)
    plot_comparison_chart(records)
    print(f"  {len(records)} configuration(s) compared.")


if __name__ == "__main__":
    main()
