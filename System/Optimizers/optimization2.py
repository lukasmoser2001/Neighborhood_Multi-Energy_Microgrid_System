from pathlib import Path
import sys
import numpy as np
import pandas as pd

from pymoo.core.problem import Problem
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize
from pymoo.termination import get_termination


CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Configurations.configurations import apply_configuration
from data_loading import (
    BASE_DIR,
    COMPONENT_PARAMETERS_FILE,
    ELECTRICITY_DATA_FILE,
    THERMAL_DATA_FILE,
    SOLAR_DATA_FILE,
    read_electricity_demand,
    read_thermal_demand,
    read_solar_data,
    load_heat_pump_cop_series,
    load_component_parameters,
    upscale_demand_series,
)
from simulation import evaluate_configuration_full_year


# Load reference annual results for Configuration A
REF_RESULTS_PATH = BASE_DIR / "Results" / "annual_results_A_grid_gb.csv"
_ref_df = pd.read_csv(REF_RESULTS_PATH)
# Assumes the CSV has columns named exactly as below
C_REF = float(_ref_df.loc[0, "annual_cost_total_eur"])
E_REF = float(_ref_df.loc[0, "annual_emissions_total_kg"])


class NeighborhoodCostProblem(Problem):
    def __init__(self, config_id: str):
        self.config_id = config_id
        self.N_PV_min = 0.0
        self.N_PV_max = 40.0
        self.E_BESS_min = 0.0
        self.E_BESS_max = 30.0
        self.E_TESS_min = 0.0
        self.E_TESS_max = 40.0
        xl = np.array([self.N_PV_min, self.E_BESS_min, self.E_TESS_min])
        xu = np.array([self.N_PV_max, self.E_BESS_max, self.E_TESS_max])
        super().__init__(
            n_var=3,
            # Multi-objective: cost and emissions
            n_obj=2,
            n_constr=0,
            xl=xl,
            xu=xu,
        )

    def _evaluate(self, X, out, *args, **kwargs):
        F_raw = []
        F_norm = []
        for row in X:
            n_pv_hh, e_bess_cap, e_tess_cap = row
            cost, emissions = run_annual_cost_and_emissions(
                config_id=self.config_id,
                n_pv_hh=float(n_pv_hh),
                e_bess_cap=float(e_bess_cap),
                e_tess_cap=float(e_tess_cap),
            )
            # Raw objectives (used by NSGA-II for now)
            F_raw.append([cost, emissions])
            # Normalized objectives with respect to configuration A
            F_norm.append([cost / C_REF, emissions / E_REF])

        # Use raw objectives for optimization for now
        out["F"] = np.array(F_raw)
        # Keep normalized objectives for potential post-processing or alternative formulations
        out["F_raw"] = np.array(F_raw)
        out["F_norm"] = np.array(F_norm)


def load_all_timeseries():
    base_component_config = load_component_parameters(COMPONENT_PARAMETERS_FILE)
    ups = base_component_config["neighborhood_upscaling"]
    n_households = int(ups["n_households"])
    sigma_log_elec = float(ups["sigma_log_electricity"])
    sigma_log_thermal = float(ups["sigma_log_thermal"])
    coincidence_alpha = float(ups["coincidence_alpha"])
    seed_offset_elec = int(ups["seed_offset_electricity"])
    seed_offset_thermal = int(ups["seed_offset_thermal"])
    electricity_series = read_electricity_demand(ELECTRICITY_DATA_FILE)
    thermal_series = read_thermal_demand(THERMAL_DATA_FILE)
    solar_series = read_solar_data(SOLAR_DATA_FILE)
    heat_pump_cop_series = load_heat_pump_cop_series(THERMAL_DATA_FILE)
    electricity_series = upscale_demand_series(
        electricity_series,
        n_households=n_households,
        sigma_log=sigma_log_elec,
        coincidence_alpha=coincidence_alpha,
        seed=n_households + seed_offset_elec,
    )
    thermal_series = upscale_demand_series(
        thermal_series,
        n_households=n_households,
        sigma_log=sigma_log_thermal,
        coincidence_alpha=coincidence_alpha,
        seed=n_households + seed_offset_thermal,
    )
    return electricity_series, thermal_series, solar_series, heat_pump_cop_series


def run_annual_cost_and_emissions(
    config_id: str,
    n_pv_hh: float,
    e_bess_cap: float,
    e_tess_cap: float,
) -> tuple[float, float]:
    base_component_config = load_component_parameters(COMPONENT_PARAMETERS_FILE)
    component_config = apply_configuration(base_component_config, config_id)
    if "pv_system" in component_config:
        component_config["pv_system"]["panels_per_household"] = float(n_pv_hh)
    if "BESS" in component_config:
        component_config["BESS"]["E_BES_cap"] = float(e_bess_cap)
    if "TESS" in component_config:
        component_config["TESS"]["E_TESS_cap"] = float(e_tess_cap)

    electricity_series, thermal_series, solar_series, heat_pump_cop_series = load_all_timeseries()
    result = evaluate_configuration_full_year(
        component_config,
        electricity_series,
        thermal_series,
        solar_series,
        heat_pump_cop_series,
    )
    cost = float(result["annual_cost_total_eur"])
    emissions = float(result["annual_emissions_total_kg"])
    return cost, emissions


def run_nsga2_for_config(config_id: str) -> dict:
    problem = NeighborhoodCostProblem(config_id=config_id)
    algorithm = NSGA2(
        pop_size=20,
        eliminate_duplicates=True,
    )
    termination = get_termination("n_gen", 20)
    res = minimize(
        problem=problem,
        algorithm=algorithm,
        termination=termination,
        seed=1,
        save_history=True,
        verbose=True,
    )
    X = np.asarray(res.X)
    F = np.asarray(res.F)

    # For multi-objective, there is no single "best"; store the Pareto front
    pareto_cost = F[:, 0]
    pareto_emissions = F[:, 1]

    out_dir = BASE_DIR / "Results" / "Optimization" / f"nsga2_{config_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Store Pareto solutions
    df_pareto = pd.DataFrame(
        {
            "N_PV_hh": X[:, 0],
            "E_BESS_cap_kwh": X[:, 1],
            "E_TESS_cap_kwh": X[:, 2],
            "annual_cost_total_eur": pareto_cost,
            "annual_emissions_total_kg": pareto_emissions,
        }
    )
    df_pareto.to_csv(out_dir / "pareto_solutions.csv", index=False)

    # Plot Pareto frontier
    import matplotlib.pyplot as plt

    plt.figure(figsize=(6, 4))
    plt.scatter(pareto_cost, pareto_emissions, c="tab:blue", s=30)
    plt.xlabel("Annual cost [EUR/year]")
    plt.ylabel("Annual emissions [kg CO2eq/year]")
    plt.title(f"Pareto frontier for configuration {config_id}")
    plt.grid(True, alpha=0.4)
    plt.tight_layout()
    plt.savefig(out_dir / "pareto_front.png", dpi=300)
    plt.close()

    # If history is available, track best cost/emissions over generations
    if res.history is not None and len(res.history) > 0:
        gen_idx = []
        best_cost = []
        best_emissions = []
        for i, h in enumerate(res.history):
            F_gen = np.asarray(h.pop.get("F"))
            # Record minimum cost and minimum emissions in each generation
            gen_idx.append(i)
            best_cost.append(F_gen[:, 0].min())
            best_emissions.append(F_gen[:, 1].min())

        df_progress = pd.DataFrame(
            {
                "generation": gen_idx,
                "best_cost_eur": best_cost,
                "best_emissions_kg": best_emissions,
            }
        )
        df_progress.to_csv(out_dir / "optimization_progress.csv", index=False)

        plt.figure(figsize=(6, 4))
        plt.plot(gen_idx, best_cost, label="Best cost", color="tab:blue")
        plt.xlabel("Generation")
        plt.ylabel("Cost [EUR/year]")
        plt.title(f"Cost progression for configuration {config_id}")
        plt.grid(True, alpha=0.4)
        plt.tight_layout()
        plt.savefig(out_dir / "progress_cost.png", dpi=300)
        plt.close()

        plt.figure(figsize=(6, 4))
        plt.plot(gen_idx, best_emissions, label="Best emissions", color="tab:green")
        plt.xlabel("Generation")
        plt.ylabel("Emissions [kg CO2eq/year]")
        plt.title(f"Emissions progression for configuration {config_id}")
        plt.grid(True, alpha=0.4)
        plt.tight_layout()
        plt.savefig(out_dir / "progress_emissions.png", dpi=300)
        plt.close()

    return {
        "config_id": config_id,
        "pareto_solutions_file": str(out_dir / "pareto_solutions.csv"),
    }


def main_opt() -> None:
    records = []
    for cfg in ["C_grid_eb_pv_bess", "D_grid_ashp_pv_bess_tess"]:
        records.append(run_nsga2_for_config(cfg))
    df = pd.DataFrame(records)
    out_path = BASE_DIR / "Results" / "Tables" / "nsga2_pareto_summary_CD.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"NSGA-II Pareto summaries for C and D written to {out_path}")


if __name__ == "__main__":
    main_opt()
