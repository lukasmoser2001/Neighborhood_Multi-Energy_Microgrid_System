from pathlib import Path
import sys
import numpy as np
import pandas as pd

from pymoo.core.problem import ElementwiseProblem
from pymoo.core.callback import Callback
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize
from pymoo.termination import get_termination
from pymoo.parallelization import StarmapParallelization
from pymoo.operators.sampling.rnd import FloatRandomSampling
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.operators.repair.rounding import RoundingRepair
from multiprocessing.pool import Pool
from tqdm import tqdm


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


## Load reference annual results for Configuration A (gas boiler)
#REF_RESULTS_PATH = BASE_DIR / "Results" / "Tables" / "annual_results_A_grid_gb.csv"
#_ref_df = pd.read_csv(REF_RESULTS_PATH)
## Select the row corresponding to configuration A if multiple rows exist
#_ref_row = _ref_df.iloc[0]
#C_REF = float(_ref_row["annual_cost_total_eur"])
#E_REF = float(_ref_row["annual_emissions_total_kg"])


class _N_PV_RoundingRepair(RoundingRepair):
    """Repair operator that rounds only the first variable (N_PV) to the nearest
    integer while leaving E_BESS (index 1) and E_TESS (index 2) as floats.

    pymoo may pass either a 2-D population array (n_individuals x n_var) or a
    1-D single-individual array (n_var,) depending on the call site.  Both
    shapes are handled by reshaping to 2-D, applying the rounding, and then
    squeezing back to the original shape.
    """

    def do(self, problem, X, **kwargs):
        X = np.asarray(X, dtype=float)
        scalar = X.ndim == 1
        X2d = np.atleast_2d(X)
        X2d[:, 0] = np.round(X2d[:, 0])
        return X2d[0] if scalar else X2d


class TqdmCallback(Callback):
    """pymoo Callback that drives a tqdm progress bar over generations."""

    def __init__(self, n_gen: int, config_id: str) -> None:
        super().__init__()
        label = config_id[0]  # "C" or "D"
        self.pbar = tqdm(
            total=n_gen,
            desc=f"NSGA-II [{label}]",
            unit="gen",
            dynamic_ncols=True,
            colour="green",
        )

    def notify(self, algorithm) -> None:
        F = np.asarray(algorithm.pop.get("F"))
        best_cost = F[:, 0].min()
        best_em = F[:, 1].min()
        self.pbar.set_postfix(
            cost=f"{best_cost:,.2f} EUR",
            em=f"{best_em:,.2f} kg",
            refresh=False,
        )
        self.pbar.update(1)

    def close(self) -> None:
        self.pbar.close()


class NeighborhoodCostProblem(ElementwiseProblem):
    """Element-wise formulation enables pymoo's built-in parallelization.

    Variable encoding:
        x[0]  N_PV    -- number of PV panels per household (integer, rounded via repair)
        x[1]  E_BESS  -- BESS capacity in kWh (float)
        x[2]  E_TESS  -- TESS capacity in kWh (float)
    """

    def __init__(self, config_id: str, **kwargs):
        self.config_id = config_id
        self.N_PV_min: int = 0
        self.N_PV_max: int = 40
        self.E_BESS_min: float = 0.0
        self.E_BESS_max: float = 30.0
        self.E_TESS_min: float = 0.0
        self.E_TESS_max: float = 40.0
        xl = np.array([float(self.N_PV_min), self.E_BESS_min, self.E_TESS_min])
        xu = np.array([float(self.N_PV_max), self.E_BESS_max, self.E_TESS_max])
        super().__init__(
            n_var=3,
            # Multi-objective: cost and emissions
            n_obj=2,
            n_constr=0,
            xl=xl,
            xu=xu,
            **kwargs,
        )

    def _evaluate(self, x, out, *args, **kwargs):
        # N_PV is kept integer (rounded by the repair operator before evaluation)
        n_pv_hh: int = int(round(x[0]))
        e_bess_cap: float = float(x[1])
        e_tess_cap: float = float(x[2])
        cost, emissions = run_annual_cost_and_emissions(
            config_id=self.config_id,
            n_pv_hh=n_pv_hh,
            e_bess_cap=e_bess_cap,
            e_tess_cap=e_tess_cap,
        )
        # Raw objectives (used by NSGA-II for now)
        out["F"] = np.array([cost, emissions])
        # Normalized objectives with respect to configuration A
        #out["F_norm"] = np.array([cost / C_REF, emissions / E_REF])


def load_all_timeseries():
    base_component_config = load_component_parameters(COMPONENT_PARAMETERS_FILE)
    ups = base_component_config["neighborhood_upscaling"]
    n_households: int = int(ups["n_households"])
    sigma_log_elec: float = float(ups["sigma_log_electricity"])
    sigma_log_thermal: float = float(ups["sigma_log_thermal"])
    coincidence_alpha: float = float(ups["coincidence_alpha"])
    seed_offset_elec: int = int(ups["seed_offset_electricity"])
    seed_offset_thermal: int = int(ups["seed_offset_thermal"])
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
    n_pv_hh: int,
    e_bess_cap: float,
    e_tess_cap: float,
) -> tuple[float, float]:
    base_component_config = load_component_parameters(COMPONENT_PARAMETERS_FILE)
    component_config = apply_configuration(base_component_config, config_id)
    if "pv_system" in component_config:
        component_config["pv_system"]["panels_per_household"] = int(n_pv_hh)
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
    cost: float = round(float(result["annual_cost_total_eur"]), 2)
    emissions: float = round(float(result["annual_emissions_total_kg"]), 2)
    return cost, emissions


def _apply_plot_style(ax) -> None:
    """Apply consistent IEEE-ready styling to a matplotlib Axes object."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(0.8)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(direction="in", length=4, width=0.8, labelsize=9)
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.5, color="gray")


def run_nsga2_for_config(config_id: str, n_gen: int = 20, n_workers: int = 1) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker

    # Short label for titles and progress bar: "C" or "D"
    label = config_id[0]

    # Parallelise individual evaluations across worker processes using pymoo's
    # StarmapParallelization runner, which is compatible with ElementwiseProblem.
    with Pool(n_workers) as pool:
        runner = StarmapParallelization(pool.starmap)
        problem = NeighborhoodCostProblem(
            config_id=config_id,
            elementwise_runner=runner,
        )

        # -----------------------------------------------------------------
        # NSGA-II operators
        #   Sampling : FloatRandomSampling  - uniform random draw in [xl, xu]
        #   Crossover: SBX (eta=15)         - standard real-valued crossover
        #   Mutation : PM  (eta=20)         - standard real-valued mutation
        #   Repair   : _N_PV_RoundingRepair - rounds x[0] (N_PV) to integer
        #                                     after every crossover/mutation
        #                                     step; x[1]/x[2] remain floats
        # -----------------------------------------------------------------
        algorithm = NSGA2(
            pop_size=20,
            sampling=FloatRandomSampling(),
            crossover=SBX(prob=0.9, eta=15, repair=_N_PV_RoundingRepair()),
            mutation=PM(eta=20, repair=_N_PV_RoundingRepair()),
            eliminate_duplicates=True,
        )
        termination = get_termination("n_gen", n_gen)
        callback = TqdmCallback(n_gen=n_gen, config_id=config_id)

        res = minimize(
            problem=problem,
            algorithm=algorithm,
            termination=termination,
            seed=1,
            save_history=True,
            verbose=False,   # suppressed: tqdm callback handles progress display
            callback=callback,
        )

    callback.close()

    X = np.asarray(res.X)
    F = np.asarray(res.F)

    # For multi-objective, there is no single "best"; store the Pareto front
    pareto_cost = F[:, 0]
    pareto_emissions = F[:, 1]

    out_dir = BASE_DIR / "Results" / "Optimization" / f"nsga2_{config_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Store Pareto solutions
    # N_PV_hh stored as integer; E_BESS and E_TESS as floats rounded to 2 dp
    df_pareto = pd.DataFrame(
        {
            "N_PV_hh": X[:, 0].round().astype(int),
            "E_BESS_cap_kwh": X[:, 1].round(2),
            "E_TESS_cap_kwh": X[:, 2].round(2),
            "annual_cost_total_eur": np.round(pareto_cost, 2),
            "annual_emissions_total_kg": np.round(pareto_emissions, 2),
        }
    )
    df_pareto.to_csv(out_dir / "pareto_solutions.csv", index=False)

    # ------------------------------------------------------------------
    # Plot 1 - Pareto frontier
    # ------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(5.5, 4.0))
    ax.scatter(
        pareto_cost,
        pareto_emissions,
        color="#1f77b4",
        edgecolors="#0d4f8c",
        linewidths=0.5,
        s=40,
        alpha=0.85,
        zorder=3,
    )
    ax.set_xlabel("Annual cost [EUR/year]", fontsize=10)
    ax.set_ylabel("Annual emissions [kg CO\u2082eq/year]", fontsize=10)
    ax.set_title(f"Pareto frontier \u2013 Configuration {label}", fontsize=11, fontweight="bold")
    _apply_plot_style(ax)
    fig.tight_layout()
    fig.savefig(out_dir / "pareto_front.pdf", dpi=300, bbox_inches="tight")
    plt.close(fig)

    # ------------------------------------------------------------------
    # Plot 2 - Optimization progress (cost and emissions vs. generation)
    # ------------------------------------------------------------------
    if res.history is not None and len(res.history) > 0:
        gen_idx = []
        best_cost = []
        best_emissions = []
        for i, h in enumerate(res.history):
            F_gen = np.asarray(h.pop.get("F"))
            # Record minimum cost and minimum emissions in each generation
            gen_idx.append(i + 1)
            best_cost.append(round(float(F_gen[:, 0].min()), 2))
            best_emissions.append(round(float(F_gen[:, 1].min()), 2))

        df_progress = pd.DataFrame(
            {
                "generation": gen_idx,
                "best_cost_eur": best_cost,
                "best_emissions_kg": best_emissions,
            }
        )
        df_progress.to_csv(out_dir / "optimization_progress.csv", index=False)

        # Combined plot: cost and emissions vs generation (two y-axes)
        fig, ax1 = plt.subplots(figsize=(5.5, 4.0))
        color_cost = "#1f77b4"
        color_em = "#2ca02c"

        ax1.plot(
            gen_idx,
            best_cost,
            color=color_cost,
            linewidth=1.2,
            label="Best cost",
        )
        ax1.set_xlabel("Generation", fontsize=10)
        ax1.set_ylabel("Cost [EUR/year]", color=color_cost, fontsize=10)
        ax1.tick_params(axis="y", labelcolor=color_cost, direction="in", length=4, width=0.8)
        ax1.tick_params(axis="x", direction="in", length=4, width=0.8)
        ax1.spines["top"].set_visible(False)
        ax1.spines["left"].set_linewidth(0.8)
        ax1.spines["bottom"].set_linewidth(0.8)
        ax1.grid(True, linestyle="--", linewidth=0.5, alpha=0.5, color="gray")

        ax2 = ax1.twinx()
        ax2.plot(
            gen_idx,
            best_emissions,
            color=color_em,
            linewidth=1.2,
            linestyle="--",
            label="Best emissions",
        )
        ax2.set_ylabel("Emissions [kg CO\u2082eq/year]", color=color_em, fontsize=10)
        ax2.tick_params(axis="y", labelcolor=color_em, direction="in", length=4, width=0.8)
        ax2.spines["top"].set_visible(False)
        ax2.spines["right"].set_linewidth(0.8)

        # Combined legend
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(
            lines1 + lines2,
            labels1 + labels2,
            fontsize=8,
            framealpha=0.9,
            edgecolor="lightgray",
            loc="upper right",
        )

        fig.suptitle(f"Optimization progression \u2013 {label}", fontsize=11, fontweight="bold")
        fig.tight_layout()
        fig.savefig(out_dir / "progress_combined.pdf", dpi=300, bbox_inches="tight")
        plt.close(fig)


def main_opt() -> None:
    for cfg in ["C_grid_eb_pv_bess", "D_grid_ashp_pv_bess_tess"]:
        run_nsga2_for_config(cfg)


if __name__ == "__main__":
    main_opt()
