from pathlib import Path
import numpy as np
import pandas as pd

from pymoo.core.problem import Problem
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize
from pymoo.termination import get_termination

from Configurations.configurations import apply_configuration
from Components import (
    UtilityGrid,
    PVSystem,
    GasBoiler,
    ElectricBoiler,
    HeatPumpAir,
    BatteryStorage,
    ThermalEnergyStorage,
)
from data_loading import (
    BASE_DIR,
    COMPONENT_PARAMETERS_FILE,
    read_electricity_demand,
    read_thermal_demand,
    read_solar_data,
    load_heat_pump_cop_series,
    load_component_parameters,
    upscale_demand_series,
)


class NeighborhoodCostProblem(Problem):
    """Single-objective annual_cost_total minimization for a given configuration.

    Decision variables (per household or equivalent):
      x[0] = N_PV_hh       (number of PV panels per household)
      x[1] = E_BESS_cap    (BESS capacity in kWh)
      x[2] = E_TESS_cap    (TESS capacity in kWh thermal)
    """

    def __init__(self, config_id: str):
        self.config_id = config_id

        # Individual bounds for clarity
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
        """Evaluate population X and return annual_cost_total for each row."""
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


def build_components_for_config(
    config_id: str,
    n_pv_hh: float,
    e_bess_cap: float,
    e_tess_cap: float,
    heat_pump_cop_series,
):
    """Construct component instances for a given configuration and design vector.

    This function loads the base component configuration from JSON, applies the
    chosen configuration, overwrites PV/BESS/TESS design variables, and then
    instantiates component objects.
    """
    base_component_config = load_component_parameters(COMPONENT_PARAMETERS_FILE)
    component_config = apply_configuration(base_component_config, config_id)

    # Overwrite only optimised design parameters according to current schema
    if "pv_system" in component_config:
        component_config["pv_system"]["panels_per_household"] = float(n_pv_hh)
    if "BESS" in component_config:
        component_config["BESS"]["E_BES_cap"] = float(e_bess_cap)
    if "TESS" in component_config:
        component_config["TESS"]["E_TESS_cap"] = float(e_tess_cap)

    components: dict[str, object] = {}

    if component_config["utility_grid"].get("enabled", True):
        components["grid"] = UtilityGrid(component_config["utility_grid"])

    if component_config["pv_system"].get("enabled", False):
        components["pv"] = PVSystem(component_config["pv_system"])

    if component_config["gas_boiler"].get("enabled", False):
        components["gas_boiler"] = GasBoiler(component_config["gas_boiler"])

    if component_config["electric_boiler"].get("enabled", False):
        components["electric_boiler"] = ElectricBoiler(component_config["electric_boiler"])

    if component_config["heat_pump_air"].get("enabled", False):
        components["heat_pump_air"] = HeatPumpAir(
            component_config["heat_pump_air"],
            cop_series=heat_pump_cop_series,
        )

    if component_config.get("BESS", {}).get("enabled", False):
        components["bess"] = BatteryStorage(component_config.get("BESS", {}))

    if component_config.get("TESS", {}).get("enabled", False):
        components["tess"] = ThermalEnergyStorage(component_config.get("TESS", {}))

    return components, component_config


def load_all_timeseries():
    """Load and upscale demand and solar series using shared data_loading helpers."""
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
    """Wrapper that runs a full-year simulation and returns annual_cost_total.

    This function reuses the aggregation logic from simulation.py's
    run_single_configuration but without writing any CSV or plotting.
    """
    # Import here to avoid circular import between optimization and simulation
    from simulation import run_period_simulation

    electricity_series, thermal_series, solar_series, heat_pump_cop_series = load_all_timeseries()

    components, component_config = build_components_for_config(
        config_id=config_id,
        n_pv_hh=n_pv_hh,
        e_bess_cap=e_bess_cap,
        e_tess_cap=e_tess_cap,
        heat_pump_cop_series=heat_pump_cop_series,
    )

    annualization_factor = component_config["annualization"]["factor"]

    full_year_results = run_period_simulation(
        components,
        annualization_factor,
        electricity_series,
        thermal_series,
        solar_series,
        start_index_electricity=0,
        start_index_thermal=0,
        start_index_solar=0,
        length=len(electricity_series),
        label=None,
    )

    # Aggregate annual cost exactly as in simulation.run_single_configuration
    total_cost_pv_om = sum(r.get("cost_pv_om_eur", 0.0) for r in full_year_results)
    total_cost_pv_capex = sum(r.get("cost_pv_capex_hour_eur", 0.0) for r in full_year_results)
    total_cost_grid = sum(r.get("cost_grid_eur", 0.0) for r in full_year_results)
    total_revenue_grid = sum(r.get("grid_revenue_eur", 0.0) for r in full_year_results)
    total_cost_gas_boiler = sum(r.get("cost_gas_boiler_eur", 0.0) for r in full_year_results)
    total_cost_electric_boiler = sum(r.get("cost_electric_boiler_eur", 0.0) for r in full_year_results)
    total_cost_heat_pump = sum(r.get("cost_heat_pump_eur", 0.0) for r in full_year_results)
    total_cost_bess = sum(r.get("cost_bess_eur", 0.0) for r in full_year_results)
    total_cost_tess = sum(r.get("cost_tess_eur", 0.0) for r in full_year_results)

    annual_cost_pv_capex_total = total_cost_pv_capex
    annual_cost_pv_om = total_cost_pv_om
    annual_cost_grid = total_cost_grid
    annual_revenue_grid = total_revenue_grid
    annual_cost_gas_boiler = total_cost_gas_boiler
    annual_cost_electric_boiler = total_cost_electric_boiler
    annual_cost_heat_pump = total_cost_heat_pump
    annual_cost_bess = total_cost_bess
    annual_cost_tess = total_cost_tess

    annual_cost_total = (
        annual_cost_pv_capex_total
        + annual_cost_pv_om
        + annual_cost_grid
        - annual_revenue_grid
        + annual_cost_gas_boiler
        + annual_cost_electric_boiler
        + annual_cost_heat_pump
        + annual_cost_bess
        + annual_cost_tess
    )

    return float(annual_cost_total)


def run_nsga2_for_config(config_id: str) -> dict:
    """Run a small NSGA-II optimisation for one configuration and return best design."""
    problem = NeighborhoodCostProblem(config_id=config_id)

    algorithm = NSGA2(
        pop_size=20,
        eliminate_duplicates=True,
    )
    termination = get_termination("n_gen", 30)

    res = minimize(
        problem=problem,
        algorithm=algorithm,
        termination=termination,
        seed=1,
        save_history=False,
        verbose=True,
    )

    F = res.F.flatten()
    X = res.X
    best_idx = F.argmin()
    best_x = X[best_idx]
    best_f = F[best_idx]

    return {
        "config_id": config_id,
        "N_PV_hh": best_x[0],
        "E_BESS_cap_kwh": best_x[1],
        "E_TESS_cap_kwh": best_x[2],
        "annual_cost_total_eur": best_f,
    }


def main_opt() -> None:
    records = []
    for cfg in ["C_grid_eb_pv_bess", "D_grid_ashp_pv_bess_tess"]:
        records.append(run_nsga2_for_config(cfg))

    df = pd.DataFrame(records)
    out_path = BASE_DIR / "Results" / "Tables" / "nsga2_best_designs_CD.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"NSGA-II best designs for C and D written to {out_path}")


if __name__ == "__main__":
    main_opt()
