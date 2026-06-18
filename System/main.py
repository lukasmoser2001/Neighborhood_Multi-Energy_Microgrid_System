from pathlib import Path
import csv
import json
import matplotlib
matplotlib.use("Agg")  # non-interactive backend, safe for scripts without a display
import matplotlib.pyplot as plt
from Components import (
    UtilityGrid,
    PVSystem,
    GasBoiler,
    ElectricBoiler,
    HeatPumpAir,
    HeatPumpGround,
    BatteryStorage,
    ThermalEnergyStorage,
)

# File paths and column names
BASE_DIR = Path(__file__).resolve().parent.parent
COMPONENT_PARAMETERS_FILE = BASE_DIR / "Data" / "Components" / "component_parameters.json"

SEASON_FILES = [
    (
        "Winter",
        BASE_DIR / "Data" / "Load" / "Electricity" / "extracted_gas_house_15_01_2023.csv",
        BASE_DIR / "Data" / "Load" / "Heat" / "extracted_when2heat_FR_15_01_2015.csv",
    ),
    (
        "Spring",
        BASE_DIR / "Data" / "Load" / "Electricity" / "extracted_gas_house_15_04_2023.csv",
        BASE_DIR / "Data" / "Load" / "Heat" / "extracted_when2heat_FR_15_04_2015.csv",
    ),
    (
        "Summer",
        BASE_DIR / "Data" / "Load" / "Electricity" / "extracted_gas_house_15_07_2023.csv",
        BASE_DIR / "Data" / "Load" / "Heat" / "extracted_when2heat_FR_15_07_2015.csv",
    ),
    (
        "Autumn",
        BASE_DIR / "Data" / "Load" / "Electricity" / "extracted_gas_house_25_10_2022.csv",
        BASE_DIR / "Data" / "Load" / "Heat" / "extracted_when2heat_FR_15_10_2015.csv",
    ),
]

# Solar irradiation data file (single file for all seasons)
SOLAR_DATA_FILE = BASE_DIR / "Data" / "OtherFactors" / "SolarIrradiation" / "It_Tamb_Compiegne_2023.csv"
ELECTRICITY_COLUMN_NAME = "Mean"
THERMAL_SPACE_COLUMN = "FR_heat_demand_space_SFH"
THERMAL_WATER_COLUMN = "FR_heat_demand_water"


def parse_float(value: str) -> float:
    # Convert CSV text values to float and accept commas as decimals.
    if value is None:
        return 0.0
    return float(value.replace(",", "."))


def read_electricity_demand(path: Path) -> list[float]:
    # Read hourly electricity demand from CSV.
    values = []
    with path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            demand = parse_float(row[ELECTRICITY_COLUMN_NAME])
            values.append(demand)
    return values


def read_thermal_demand(path: Path) -> list[float]:
    # Read hourly thermal demand and sum space and water heating.
    values = []
    with path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            space = parse_float(row[THERMAL_SPACE_COLUMN])
            water = parse_float(row[THERMAL_WATER_COLUMN])
            values.append(space + water)
    return values


def read_solar_data(path: Path) -> list[tuple[float, float]]:
    # Read hourly solar irradiance and ambient temperature data.
    values = []
    with path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            irradiance = parse_float(row["I(t)_Wm2"])
            T_amb = parse_float(row["Tamb_C"])
            values.append((irradiance, T_amb))
    return values


def load_component_parameters(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Component parameters file not found: {path}")
    with path.open("r", encoding="utf-8") as jsonfile:
        return json.load(jsonfile)


def apply_component_parameters(config: dict) -> dict:
    # Instantiate and return only enabled components from configuration.
    # Component parameter descriptions live as comments in System/Components/components.py
    components = {}

    if config["utility_grid"].get("enabled", True):
        components["grid"] = UtilityGrid(config["utility_grid"])

    if config["pv_system"].get("enabled", True):
        components["pv"] = PVSystem(config["pv_system"])

    if config["gas_boiler"].get("enabled", False):
        components["gas_boiler"] = GasBoiler(config["gas_boiler"])

    if config["electric_boiler"].get("enabled", False):
        components["electric_boiler"] = ElectricBoiler(config["electric_boiler"])

    if config["heat_pump_air"].get("enabled", False):
        components["heat_pump_air"] = HeatPumpAir(config["heat_pump_air"])

    if config["heat_pump_ground"].get("enabled", False):
        components["heat_pump_ground"] = HeatPumpGround(config["heat_pump_ground"])

    if config.get("BESS", {}).get("enabled", False):
        components["bess"] = BatteryStorage(config.get("BESS", {}))

    if config.get("TESS", {}).get("enabled", False):
        components["tess"] = ThermalEnergyStorage(config.get("TESS", {}))

    return components


def write_hourly_results(path: Path, rows: list[dict]) -> None:
    # Write hourly results to a CSV file.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_annual_results(path: Path, summary: dict) -> None:
    # Write annual summary results to a CSV file.
    fieldnames = [
        "total_electricity_demand_kwh",
        "total_electricity_consumption_kwh",
        "total_thermal_demand_kwh",
        "total_pv_generation_kwh",
        "pv_self_consumption_fraction",
        "annual_cost_pv_capex_eur",
        "annual_cost_pv_om_eur",
        "annual_cost_grid_eur",
        "annual_cost_gas_boiler_eur",
        "annual_cost_electric_boiler_eur",
        "annual_cost_heat_pump_eur",
        "annual_cost_bess_eur",
        "annual_cost_tess_eur",
        "annual_cost_total_eur",
        "annual_emissions_grid_kg",
        "annual_emissions_gas_boiler_kg",
        "annual_emissions_electric_boiler_kg",
        "annual_emissions_bess_kg",
        "annual_emissions_tess_kg",
        "annual_emissions_total_kg",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(summary)


def build_component_suffix(components: dict) -> str:
    # Build a short filename suffix from enabled component abbreviations.
    abbrevs = []
    if "pv" in components:
        abbrevs.append("pv")
    if "heat_pump_air" in components:
        abbrevs.append("hpa")
    if "heat_pump_ground" in components:
        abbrevs.append("hpg")
    if "gas_boiler" in components:
        abbrevs.append("gb")
    if "electric_boiler" in components:
        abbrevs.append("eb")
    if "bess" in components:
        abbrevs.append("bess")
    if "tess" in components:
        abbrevs.append("tess")
    return "_".join(abbrevs) if abbrevs else "base"


def plot_seasonal_energy_diagrams(hourly_results: list[dict], components: dict) -> None:
    # Generate and save electrical and thermal energy diagrams for each season.

    season_order = ["Winter", "Spring", "Summer", "Autumn"]
    component_suffix = build_component_suffix(components)

    electric_cols = [
        "electricity_demand_kwh",
        "total_electricity_consumption_kwh",
        "grid_supply_kwh",
        "grid_export_kwh",
    ]
    if "pv" in components:
        electric_cols.append("pv_output_kwh")
    if "heat_pump_air" in components or "heat_pump_ground" in components:
        electric_cols.append("heat_pump_electric_demand_kwh")
    if "electric_boiler" in components:
        electric_cols.append("electric_boiler_electric_demand_kwh")
    if "bess" in components:
        electric_cols.append("bess_soc_kwh")

    thermal_cols = ["thermal_demand_kwh"]
    if "heat_pump_air" in components or "heat_pump_ground" in components:
        thermal_cols.append("heat_pump_heat_kwh")
    if "gas_boiler" in components:
        thermal_cols.append("gas_boiler_heat_kwh")
    if "electric_boiler" in components:
        thermal_cols.append("electric_boiler_heat_kwh")
    if "tess" in components:
        thermal_cols.append("tess_soc_kwh")

    legend_labels = {
        # electricity energy diagram labels
        "electricity_demand_kwh": "Demand",
        "total_electricity_consumption_kwh": "Total elec.",
        "pv_output_kwh": "PV output",
        "grid_supply_kwh": "Grid import",
        "grid_export_kwh": "Grid export",
        "heat_pump_electric_demand_kwh": "HP elec.",
        "electric_boiler_electric_demand_kwh": "EB elec.",
        "bess_soc_kwh": "BESS SOC",
        # thermal energy diagram labels
        "tess_soc_kwh": "TESS SOC",
        "thermal_demand_kwh": "Thermal dem.",
        "heat_pump_heat_kwh": "HP heat",
        "gas_boiler_heat_kwh": "Gas boiler",
        "electric_boiler_heat_kwh": "EB heat",
    }
    colors = {
        "electricity_demand_kwh": "#1f77b4",              # blue
        "total_electricity_consumption_kwh": "#ff7f0e",  # orange
        "pv_output_kwh": "#f7c948",                       # yellow
        "grid_supply_kwh": "#17becf",                     # cyan
        "grid_export_kwh": "#aec7e8",                     # light blue
        "heat_pump_electric_demand_kwh": "#2ca02c",       # green
        "electric_boiler_electric_demand_kwh": "#d62728", # red
        "bess_soc_kwh": "#9467bd",                        # purple
        "thermal_demand_kwh": "#8c564b",                  # brown
        "heat_pump_heat_kwh": "#e377c2",                  # pink
        "gas_boiler_heat_kwh": "#7f7f7f",                 # gray
        "electric_boiler_heat_kwh": "#bcbd22",            # olive
        "tess_soc_kwh": "#17becf",                        # teal-cyan
    }

    for season in season_order:
        season_rows = sorted(
            [r for r in hourly_results if r["season"] == season],
            key=lambda r: r["hour"],
        )

        if not season_rows:
            continue

        hours = [r["hour"] for r in season_rows]
        season_slug = season.lower()

        # Electrical energy diagram
        fig, ax = plt.subplots(figsize=(10, 6))
        for col in electric_cols:
            ax.plot(
                hours,
                [r[col] for r in season_rows],
                label=legend_labels[col],
                color=colors[col],
                linewidth=2,
            )
        ax.set_title(f"{season} — Electrical Energy")
        ax.set_xlabel("Time [h]")
        ax.set_ylabel("Electrical energy [kWh]")
        ax.set_xlim(1, 24)
        ax.set_xticks(range(1, 25))
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend()
        el_output = BASE_DIR / "Results" / f"{season_slug}_el_{component_suffix}.png"
        fig.tight_layout()
        fig.savefig(el_output, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"  diagram saved: {el_output}")

        # Thermal energy diagram
        fig, ax = plt.subplots(figsize=(10, 6))
        for col in thermal_cols:
            ax.plot(
                hours,
                [r[col] for r in season_rows],
                label=legend_labels[col],
                color=colors[col],
                linewidth=2,
            )
        ax.set_title(f"{season} — Thermal Energy")
        ax.set_xlabel("Time [h]")
        ax.set_ylabel("Thermal energy [kWh]")
        ax.set_xlim(1, 24)
        ax.set_xticks(range(1, 25))
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend()
        th_output = BASE_DIR / "Results" / f"{season_slug}_th_{component_suffix}.png"
        fig.tight_layout()
        fig.savefig(th_output, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"  diagram saved: {th_output}")


def main() -> None:
    # Load component parameters and instantiate only enabled components
    component_config = load_component_parameters(COMPONENT_PARAMETERS_FILE)
    components = apply_component_parameters(component_config)
    annualization_factor = component_config["annualization"]["factor"]

    # Extract enabled components
    grid = components.get("grid")
    pv = components.get("pv")
    gas_boiler = components.get("gas_boiler")
    electric_boiler = components.get("electric_boiler")
    heat_pump_air = components.get("heat_pump_air")
    heat_pump_ground = components.get("heat_pump_ground")
    bess = components.get("bess")
    tess = components.get("tess")

    # Read data, compute hourly results, and write outputs.
    hourly_results = []
    total_electricity_demand = 0.0
    total_electricity_consumption = 0.0
    total_thermal_demand = 0.0
    total_pv_generation = 0.0
    total_pv_used = 0.0
    total_cost_pv_capex = 0.0
    total_cost_pv_om = 0.0
    total_cost_grid = 0.0
    total_cost_gas_boiler = 0.0
    total_cost_electric_boiler = 0.0
    total_cost_heat_pump = 0.0
    total_cost_bess = 0.0
    total_cost_tess = 0.0
    total_emissions_grid = 0.0
    total_emissions_gas_boiler = 0.0
    total_emissions_electric_boiler = 0.0
    total_emissions_bess = 0.0
    total_emissions_tess = 0.0

    # Read all solar data (full year from Jan 1, 2023)
    all_solar_data = read_solar_data(SOLAR_DATA_FILE)

    # Hour indices for representative days: Jan 15, Apr 15, Jul 15, Oct 15
    # (Data starts Jan 1 00:00, so hour 336 = Jan 15, 2496 = Apr 15, etc.)
    SEASON_HOUR_INDICES = [
        336,   # Winter (Jan 15): hours 336-359
        2496,  # Spring (Apr 15): hours 2496-2519
        4680,  # Summer (Jul 15): hours 4680-4703
        6888,  # Autumn (Oct 15): hours 6888-6911
    ]

    for season_index, (season_name, electricity_path, thermal_path) in enumerate(SEASON_FILES):
        electricity_demand = [
            demand / 1000.0 for demand in read_electricity_demand(electricity_path)
        ]
        thermal_demand = [
            demand / 1000.0 for demand in read_thermal_demand(thermal_path)
        ]

        # Extract 24-hour solar data block for this season
        start_hour = SEASON_HOUR_INDICES[season_index]
        end_hour = start_hour + 24
        season_solar_data = all_solar_data[start_hour:end_hour]

        for hour_index, (electricity_kwh, thermal_kwh) in enumerate(
            zip(electricity_demand, thermal_demand), start=1
        ):
            # Get solar data for this hour
            if hour_index - 1 < len(season_solar_data):
                irradiance, T_amb = season_solar_data[hour_index - 1]
            else:
                # Fallback to zero if not enough data
                irradiance, T_amb = 0.0, 20.0

            # Calculate PV output if PV is enabled
            pv_output_kwh = 0.0
            pv_cell_temp_c = 0.0
            if pv:
                pv_output_kwh = pv.calc_pv_output_kwh(irradiance, T_amb)
                pv_cell_temp_c = pv.calc_pv_temperature(T_amb, irradiance)

            # Thermal Energy balance
            gas_boiler_heat_kwh = 0.0
            electric_boiler_heat_kwh = 0.0
            heat_pump_heat_kwh = 0.0
            heat_pump_electric_demand_kwh = 0.0
            electric_boiler_electric_demand_kwh = 0.0
            active_heat_pump = None

            if heat_pump_air:
                active_heat_pump = heat_pump_air
            elif heat_pump_ground:
                active_heat_pump = heat_pump_ground

            if active_heat_pump:
                heat_pump_heat_kwh = thermal_kwh
                heat_pump_electric_demand_kwh = active_heat_pump.get_electricity_demand_kwh(
                    thermal_kwh, season_index, hour_index - 1
                )
            elif electric_boiler and not gas_boiler:
                electric_boiler_heat_kwh = thermal_kwh
            elif gas_boiler and not electric_boiler:
                gas_boiler_heat_kwh = thermal_kwh
            elif gas_boiler and electric_boiler:
                electric_boiler_heat_kwh = thermal_kwh

            if tess:
                if hour_index == 1:
                    tess.reset_soc()

                tess_discharge_kwh = tess.get_discharge_for_demand(thermal_kwh)
                tess_heat_supplied = tess.get_heat_from_discharge(tess_discharge_kwh)
                remaining_thermal_demand = max(0.0, thermal_kwh - tess_heat_supplied)
            else:
                tess_discharge_kwh = 0.0
                tess_heat_supplied = 0.0
                remaining_thermal_demand = thermal_kwh

            if active_heat_pump:
                heat_pump_heat_kwh = remaining_thermal_demand
            elif electric_boiler and not gas_boiler:
                electric_boiler_heat_kwh = remaining_thermal_demand
            elif gas_boiler and not electric_boiler:
                gas_boiler_heat_kwh = remaining_thermal_demand
            elif gas_boiler and electric_boiler:
                electric_boiler_heat_kwh = remaining_thermal_demand

            tess_charge_kwh = 0.0
            if tess and tess.available_charge_capacity_kwh() > 0.0:
                tess_charge_kwh = tess.get_charge_from_heat_source(
                    heat_pump_heat_kwh + electric_boiler_heat_kwh + gas_boiler_heat_kwh
                )
                if tess_charge_kwh > 0.0:
                    if active_heat_pump:
                        heat_pump_heat_kwh += tess_charge_kwh
                    elif electric_boiler and not gas_boiler:
                        electric_boiler_heat_kwh += tess_charge_kwh
                    elif gas_boiler and not electric_boiler:
                        gas_boiler_heat_kwh += tess_charge_kwh
                    elif gas_boiler and electric_boiler:
                        electric_boiler_heat_kwh += tess_charge_kwh

            if electric_boiler and electric_boiler_heat_kwh > 0:
                electric_boiler_electric_demand_kwh = electric_boiler.get_electricity_demand_kwh(
                    electric_boiler_heat_kwh
                )

            if active_heat_pump:
                heat_pump_electric_demand_kwh = active_heat_pump.get_electricity_demand_kwh(
                    heat_pump_heat_kwh, season_index, hour_index - 1
                )

            if tess:
                tess.update_state(q_tess_in=tess_charge_kwh, q_tess_out=tess_discharge_kwh)
                tess_soc_kwh = tess.soc
            else:
                tess_soc_kwh = 0.0

            # Electricity Energy balance
            total_electricity_consumption_kwh = (
                electricity_kwh
                + electric_boiler_electric_demand_kwh
                + heat_pump_electric_demand_kwh
            )
            bess_charge_kwh = 0.0
            bess_discharge_kwh = 0.0
            if bess:
                if hour_index == 1:
                    bess.reset_soc()

                if pv_output_kwh > total_electricity_consumption_kwh:
                    surplus = pv_output_kwh - total_electricity_consumption_kwh
                    max_charge_kw = min(
                        surplus,
                        bess.P_max,
                        bess.available_charge_capacity_kwh() / bess.eta_char,
                    )
                    bess_charge_kwh = max(0.0, max_charge_kw)
                    energy_in_kwh = bess.get_charge_energy_input(bess_charge_kwh)
                    bess.apply_self_discharge()
                    bess.soc += energy_in_kwh
                elif pv_output_kwh < total_electricity_consumption_kwh:
                    deficit = total_electricity_consumption_kwh - pv_output_kwh
                    max_discharge_kw = min(
                        deficit,
                        bess.P_max,
                        bess.available_discharge_capacity_kwh() * bess.eta_disc,
                    )
                    bess_discharge_kwh = max(0.0, max_discharge_kw)
                    energy_out_kwh = bess.get_discharge_energy_output(bess_discharge_kwh)
                    bess.apply_self_discharge()
                    bess.soc -= energy_out_kwh
                else:
                    bess.apply_self_discharge()

                bess.clamp_soc()
                grid_supply_kwh = max(
                    0.0,
                    total_electricity_consumption_kwh - pv_output_kwh - bess_discharge_kwh,
                )
                grid_export_kwh = max(
                    0.0,
                    pv_output_kwh - total_electricity_consumption_kwh - bess_charge_kwh,
                )
            else:
                grid_supply_kwh = max(0.0, total_electricity_consumption_kwh - pv_output_kwh)
                grid_export_kwh = max(0.0, pv_output_kwh - total_electricity_consumption_kwh)

            pv_used_kwh = pv_output_kwh - grid_export_kwh
            bess_soc_kwh = bess.soc if bess else 0.0

            # End-of-day SOC restoration at hour 24
            if hour_index == 24:

                # BESS correction
                if bess:
                    # force_soc_to_target() internally sets bess.soc = target and returns the signed delta
                    bess_delta_kwh = bess.force_soc_to_target()

                    if bess_delta_kwh > 0.0:
                        # Deficit: grid supplies the missing electrical energy
                        grid_supply_kwh += bess_delta_kwh
                        total_electricity_consumption_kwh += bess_delta_kwh

                    elif bess_delta_kwh < 0.0:
                        # Surplus: excess electrical energy is sold back to grid
                        grid_export_kwh += abs(bess_delta_kwh)

                    # Log the corrected SOC value (already set inside force_soc_to_target)
                    bess_soc_kwh = bess.soc

                # TESS correction
                if tess:
                    tess_delta_kwh = tess.force_soc_to_target()
                    if tess_delta_kwh > 0.0:
                        thermal_kwh += tess_delta_kwh
                        # Propagate the extra demand to the active heat source
                        if active_heat_pump:
                            heat_pump_heat_kwh += tess_delta_kwh
                            heat_pump_electric_demand_kwh = active_heat_pump.get_electricity_demand_kwh(
                                heat_pump_heat_kwh, season_index, hour_index - 1
                            )
                            total_electricity_consumption_kwh += (
                                active_heat_pump.get_electricity_demand_kwh(
                                    tess_delta_kwh, season_index, hour_index - 1
                                )
                            )
                        elif electric_boiler and not gas_boiler:
                            electric_boiler_heat_kwh += tess_delta_kwh
                            extra_elec = electric_boiler.get_electricity_demand_kwh(tess_delta_kwh)
                            electric_boiler_electric_demand_kwh += extra_elec
                            total_electricity_consumption_kwh += extra_elec
                        elif gas_boiler:
                            gas_boiler_heat_kwh += tess_delta_kwh
                    # Surplus (tess_delta_kwh < 0) is discarded; no revenue for thermal
                    # Log the corrected SOC value (already set inside force_soc_to_target)
                    tess_soc_kwh = tess.soc

            # Costs
            cost_pv_capex_hour_eur = 0.0
            cost_pv_om_eur = 0.0
            if pv:
                cost_pv_capex_hour_eur = pv.get_capex_hour_eur(annualization_factor)
                cost_pv_om_eur = pv.get_om_cost_eur(pv_output_kwh)

            cost_grid_eur = 0.0
            grid_revenue_eur = 0.0
            if grid:
                cost_grid_eur = grid.get_cost_eur(grid_supply_kwh)
                grid_revenue_eur = grid.get_revenue_eur(grid_export_kwh)

            cost_gas_boiler_eur = 0.0
            if gas_boiler:
                cost_gas_boiler_eur = gas_boiler.get_cost_eur(gas_boiler_heat_kwh)

            cost_electric_boiler_eur = 0.0
            if electric_boiler:
                cost_electric_boiler_eur = electric_boiler.get_cost_eur(electric_boiler_heat_kwh)

            cost_heat_pump_eur = 0.0
            if active_heat_pump:
                cost_heat_pump_eur = active_heat_pump.get_cost_eur(heat_pump_heat_kwh)

            cost_bess_eur = 0.0
            if bess:
                cost_bess_eur = bess.LCOS * bess.E_cap / (annualization_factor * 24.0)

            cost_tess_eur = 0.0
            if tess:
                cost_tess_eur = tess.get_cost_eur(tess_discharge_kwh)

            total_cost_hour_eur = (
                cost_pv_capex_hour_eur
                + cost_pv_om_eur
                + cost_grid_eur
                - grid_revenue_eur
                + cost_gas_boiler_eur
                + cost_electric_boiler_eur
                + cost_heat_pump_eur
                + cost_bess_eur
                + cost_tess_eur
            )

            # Emissions
            emissions_grid_kg = 0.0
            if grid:
                emissions_grid_kg = grid.get_emissions_kg(grid_supply_kwh)

            emissions_gas_boiler_kg = 0.0
            if gas_boiler:
                emissions_gas_boiler_kg = gas_boiler.get_emissions_kg(gas_boiler_heat_kwh)

            emissions_electric_boiler_kg = 0.0
            if electric_boiler:
                emissions_electric_boiler_kg = electric_boiler.get_emissions_kg(electric_boiler_heat_kwh)

            emissions_heat_pump_kg = 0.0
            emissions_bess_kg = 0.0
            emissions_tess_kg = 0.0
            if tess:
                emissions_tess_kg = tess.get_emissions_kg(tess_discharge_kwh)

            total_emissions_hour_kg = (
                emissions_grid_kg
                + emissions_gas_boiler_kg
                + emissions_electric_boiler_kg
                + emissions_heat_pump_kg
                + emissions_bess_kg
                + emissions_tess_kg
            )

            # Accumulate annual totals
            total_electricity_demand += electricity_kwh
            total_electricity_consumption += total_electricity_consumption_kwh
            total_thermal_demand += thermal_kwh
            total_pv_generation += pv_output_kwh
            total_pv_used += pv_used_kwh
            total_cost_pv_capex += cost_pv_capex_hour_eur
            total_cost_pv_om += cost_pv_om_eur
            total_cost_grid += cost_grid_eur
            total_cost_gas_boiler += cost_gas_boiler_eur
            total_cost_electric_boiler += cost_electric_boiler_eur
            total_cost_heat_pump += cost_heat_pump_eur
            total_cost_bess += cost_bess_eur
            total_cost_tess += cost_tess_eur
            total_emissions_grid += emissions_grid_kg
            total_emissions_gas_boiler += emissions_gas_boiler_kg
            total_emissions_electric_boiler += emissions_electric_boiler_kg
            total_emissions_bess += emissions_bess_kg
            total_emissions_tess += emissions_tess_kg

            hourly_results.append(
                {
                    "season": season_name,
                    "hour": hour_index,
                    "electricity_demand_kwh": round(electricity_kwh, 4),
                    "total_electricity_consumption_kwh": round(total_electricity_consumption_kwh, 4),
                    "heat_pump_heat_kwh": round(heat_pump_heat_kwh, 4),
                    "heat_pump_electric_demand_kwh": round(heat_pump_electric_demand_kwh, 4),
                    "electric_boiler_electric_demand_kwh": round(electric_boiler_electric_demand_kwh, 4),
                    "thermal_demand_kwh": round(thermal_kwh, 4),
                    "pv_output_kwh": round(pv_output_kwh, 4),
                    "grid_export_kwh": round(grid_export_kwh, 4),
                    "grid_revenue_eur": round(grid_revenue_eur, 4),
                    "pv_cell_temp_c": round(pv_cell_temp_c, 2),
                    "grid_supply_kwh": round(grid_supply_kwh, 4),
                    "gas_boiler_heat_kwh": round(gas_boiler_heat_kwh, 4),
                    "electric_boiler_heat_kwh": round(electric_boiler_heat_kwh, 4),
                    "bess_soc_kwh": round(bess_soc_kwh, 4),
                    "bess_charge_kwh": round(bess_charge_kwh, 4),
                    "bess_discharge_kwh": round(bess_discharge_kwh, 4),
                    "tess_soc_kwh": round(tess_soc_kwh, 4),
                    "tess_charge_kwh": round(tess_charge_kwh, 4),
                    "tess_discharge_kwh": round(tess_discharge_kwh, 4),
                    "cost_pv_capex_hour_eur": round(cost_pv_capex_hour_eur, 4),
                    "cost_pv_om_eur": round(cost_pv_om_eur, 4),
                    "cost_grid_eur": round(cost_grid_eur, 4),
                    "cost_gas_boiler_eur": round(cost_gas_boiler_eur, 4),
                    "cost_electric_boiler_eur": round(cost_electric_boiler_eur, 4),
                    "cost_heat_pump_eur": round(cost_heat_pump_eur, 4),
                    "cost_bess_eur": round(cost_bess_eur, 4),
                    "cost_tess_eur": round(cost_tess_eur, 4),
                    "total_cost_hour_eur": round(total_cost_hour_eur, 4),
                    "emissions_grid_kg": round(emissions_grid_kg, 4),
                    "emissions_gas_boiler_kg": round(emissions_gas_boiler_kg, 4),
                    "emissions_electric_boiler_kg": round(emissions_electric_boiler_kg, 4),
                    "emissions_heat_pump_kg": round(emissions_heat_pump_kg, 4),
                    "emissions_bess_kg": round(emissions_bess_kg, 4),
                    "emissions_tess_kg": round(emissions_tess_kg, 4),
                    "total_emissions_hour_kg": round(total_emissions_hour_kg, 4),
                }
            )

    # Calculate annual aggregates
    annual_electricity_demand = total_electricity_demand * annualization_factor
    annual_electricity_consumption = total_electricity_consumption * annualization_factor
    annual_thermal_demand = total_thermal_demand * annualization_factor
    annual_pv_generation = total_pv_generation * annualization_factor
    pv_self_consumption_fraction = (
        total_pv_used / total_pv_generation if total_pv_generation > 0 else 0.0
    )

    annual_cost_pv_capex_total = pv.capex_total_eur if pv else 0.0
    annual_cost_pv_capex = total_cost_pv_capex * annualization_factor
    annual_cost_pv_om = total_cost_pv_om * annualization_factor
    annual_cost_grid = total_cost_grid * annualization_factor
    annual_cost_gas_boiler = total_cost_gas_boiler * annualization_factor
    annual_cost_electric_boiler = total_cost_electric_boiler * annualization_factor
    total_cost_heat_pump = total_cost_heat_pump * annualization_factor
    annual_cost_bess = total_cost_bess * annualization_factor
    annual_cost_tess = total_cost_tess * annualization_factor
    annual_cost_total = (
        annual_cost_pv_capex_total
        + annual_cost_pv_om
        + annual_cost_grid
        + annual_cost_gas_boiler
        + annual_cost_electric_boiler
        + total_cost_heat_pump
        + annual_cost_bess
        + annual_cost_tess
    )

    annual_emissions_grid = total_emissions_grid * annualization_factor
    annual_emissions_gas_boiler = total_emissions_gas_boiler * annualization_factor
    annual_emissions_electric_boiler = total_emissions_electric_boiler * annualization_factor
    annual_emissions_bess = bess.CO2eq_BES_annual if bess else 0.0
    annual_emissions_tess = total_emissions_tess * annualization_factor
    annual_emissions_total = (
        annual_emissions_grid
        + annual_emissions_gas_boiler
        + annual_emissions_electric_boiler
        + annual_emissions_bess
        + annual_emissions_tess
    )
    # heatpump missing, because emissions are included in the grid emissions for electricity consumption
    # same would apply for electric boiler emissions, but they are calculated separately here for clarity

    # Build output filenames with component suffix
    component_suffix = build_component_suffix(components)
    output_file = BASE_DIR / "Results" / f"hourly_results_{component_suffix}.csv"
    annual_output_file = BASE_DIR / "Results" / f"annual_results_{component_suffix}.csv"

    # Write hourly results
    write_hourly_results(output_file, hourly_results)

    # Generate seasonal energy diagrams
    plot_seasonal_energy_diagrams(hourly_results, components)

    # Write annual results
    write_annual_results(
        annual_output_file,
        {
            "total_electricity_demand_kwh": round(annual_electricity_demand, 4),
            "total_electricity_consumption_kwh": round(annual_electricity_consumption, 4),
            "total_thermal_demand_kwh": round(annual_thermal_demand, 4),
            "total_pv_generation_kwh": round(annual_pv_generation, 4),
            "pv_self_consumption_fraction": round(pv_self_consumption_fraction, 4),
            "annual_cost_pv_capex_eur": round(annual_cost_pv_capex_total, 4),
            "annual_cost_pv_om_eur": round(annual_cost_pv_om, 4),
            "annual_cost_grid_eur": round(annual_cost_grid, 4),
            "annual_cost_gas_boiler_eur": round(annual_cost_gas_boiler, 4),
            "annual_cost_electric_boiler_eur": round(annual_cost_electric_boiler, 4),
            "annual_cost_heat_pump_eur": round(total_cost_heat_pump, 4),
            "annual_cost_bess_eur": round(annual_cost_bess, 4),
            "annual_cost_tess_eur": round(annual_cost_tess, 4),
            "annual_cost_total_eur": round(annual_cost_total, 4),
            "annual_emissions_grid_kg": round(annual_emissions_grid, 4),
            "annual_emissions_gas_boiler_kg": round(annual_emissions_gas_boiler, 4),
            "annual_emissions_electric_boiler_kg": round(annual_emissions_electric_boiler, 4),
            "annual_emissions_bess_kg": round(annual_emissions_bess, 4),
            "annual_emissions_tess_kg": round(annual_emissions_tess, 4),
            "annual_emissions_total_kg": round(annual_emissions_total, 4),
        },
    )

    print(f"  hourly results written to: {output_file}")
    print(f"  annual results written to: {annual_output_file}")


# Output column definitions
RESULT_FIELDS = [
    "season",
    "hour",
    "electricity_demand_kwh",
    "total_electricity_consumption_kwh",
    "heat_pump_heat_kwh",
    "heat_pump_electric_demand_kwh",
    "electric_boiler_electric_demand_kwh",
    "thermal_demand_kwh",
    "pv_output_kwh",
    "grid_export_kwh",
    "grid_revenue_eur",
    "pv_cell_temp_c",
    "grid_supply_kwh",
    "gas_boiler_heat_kwh",
    "electric_boiler_heat_kwh",
    "bess_soc_kwh",
    "bess_charge_kwh",
    "bess_discharge_kwh",
    "tess_soc_kwh",
    "tess_charge_kwh",
    "tess_discharge_kwh",
    "cost_pv_capex_hour_eur",
    "cost_pv_om_eur",
    "cost_grid_eur",
    "cost_gas_boiler_eur",
    "cost_electric_boiler_eur",
    "cost_heat_pump_eur",
    "cost_bess_eur",
    "cost_tess_eur",
    "total_cost_hour_eur",
    "emissions_grid_kg",
    "emissions_gas_boiler_kg",
    "emissions_electric_boiler_kg",
    "emissions_heat_pump_kg",
    "emissions_bess_kg",
    "emissions_tess_kg",
    "total_emissions_hour_kg",
]


if __name__ == "__main__":
    main()
