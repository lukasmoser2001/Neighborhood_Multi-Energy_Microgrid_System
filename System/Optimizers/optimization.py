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
            n_obj=1,
            n_constr=0,
            xl=xl,
            xu=xu,
        )

    def _evaluate(self, X, out, *args, **kwargs):
        F = []
        for row in X:
            n_pv_hh, e_bess_cap, e_tess_cap = row
            cost = run_annual_cost(
                config_id=self.config_id,
                n_pv_hh=float(n_pv_hh),
                e_bess_cap=float(e_bess_cap),
                e_tess_cap=float(e_tess_cap),
            )
            F.append([cost])
        out["F"] = np.array(F)


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


def run_annual_cost(
    config_id: str,
    n_pv_hh: float,
    e_bess_cap: float,
    e_tess_cap: float,
) -> float:
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
    return float(result["annual_cost_total_eur"])


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
        save_history=False,
        verbose=True,
    )
    X = np.asarray(res.X)
    F = np.asarray(res.F).flatten()

    if X.ndim == 1:
        best_x = X
        best_f = F[0] if F.size == 1 else F[F.argmin()]
    else:
        best_idx = F.argmin()
        best_x = X[best_idx]
        best_f = F[best_idx]
    return {
        "config_id": config_id,
        "N_PV_hh": float(best_x[0]),
        "E_BESS_cap_kwh": float(best_x[1]),
        "E_TESS_cap_kwh": float(best_x[2]),
        "annual_cost_total_eur": float(best_f),
    }


def main_opt() -> None:
    records = []
    for cfg in ["C_grid_eb_pv_bess", "D_grid_ashp_pv_bess_tess"]:
        records.append(run_nsga2_for_config(cfg))
    df = pd.DataFrame(records)
    out_path = BASE_DIR / "Results" / "Tables" / "nsga2_best_designs_CD_2.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"NSGA-II best designs for C and D written to {out_path}")


if __name__ == "__main__":
    main_opt()
