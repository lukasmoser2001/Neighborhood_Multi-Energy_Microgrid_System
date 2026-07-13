from datetime import datetime, timezone
from pathlib import Path
import copy
import csv
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from Components import (
    UtilityGrid,
    PVSystem,
    GasBoiler,
    ElectricBoiler,
    HeatPumpAir,
    BatteryStorage,
    ThermalEnergyStorage,
)
from Configurations.configurations import CONFIGURATIONS, apply_configuration
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

ELECTRICAL_Y_MAX = 7.0
THERMAL_Y_MAX = 12.0

CONFIG_LABELS = {
    "A_grid_gb": "A: Grid + Gas Boiler",
    "B_grid_eb": "B: Grid + Electric Boiler",
    "C_grid_eb_pv_bess": "C: Grid + Electric Boiler + PV + BESS",
    "D_grid_ashp_pv_bess_tess": "D: Grid + ASHP + PV + BESS + TESS",
}

EXAMPLE_DATES = [
    ("winter", 1, 15),
    ("spring", 4, 15),
    ("summer", 7, 15),
    ("autumn", 10, 15),
]


def apply_component_parameters(config: dict, heat_pump_cop_series: list[list[float]] | None = None) -> dict:
    components: dict[str, object] = {}

    if config["utility_grid"].get("enabled", True):
        components["grid"] = UtilityGrid(config["utility_grid"])

    if config["pv_system"].get("enabled", False):
        components["pv"] = PVSystem(config["pv_system"])

    if config["gas_boiler"].get("enabled", False):
        components["gas_boiler"] = GasBoiler(config["gas_boiler"])

    if config["electric_boiler"].get("enabled", False):
        components["electric_boiler"] = ElectricBoiler(config["electric_boiler"])

    if config["heat_pump_air"].get("enabled", False):
        components["heat_pump_air"] = HeatPumpAir(config["heat_pump_air"], cop_series=heat_pump_cop_series)

    if config.get("BESS", {}).get("enabled", False):
        components["bess"] = BatteryStorage(config.get("BESS", {}))

    if config.get("TESS", {}).get("enabled", False):
        components["tess"] = ThermalEnergyStorage(config.get("TESS", {}))

    return components


def build_result_fields(components: dict) -> list[str]:
    fields = [
        "timestamp",
        "hour",
        "electricity_demand_kwh",
        "total_electricity_consumption_kwh",
        "thermal_demand_kwh",
        "grid_supply_kwh",
    ]

    fields += [
        "cost_grid_eur",
        "cost_grid_subscription_eur",
        "total_cost_hour_eur",
        "emissions_grid_kg",
        "total_emissions_hour_kg",
    ]

    if "pv" in components:
        fields += (
            "pv_output_kwh",
            "grid_export_kwh",
            "grid_revenue_eur",
            "pv_cell_temp_c",
            "cost_pv_capex_hour_eur",
            "cost_pv_om_eur",
        )
    if "gas_boiler" in components:
        fields += ["gas_boiler_heat_kwh", "cost_gas_boiler_eur", "emissions_gas_boiler_kg"]
    if "electric_boiler" in components:
        fields += [
            "electric_boiler_heat_kwh",
            "electric_boiler_electric_demand_kwh",
            "cost_electric_boiler_eur",
            "emissions_electric_boiler_kg",
        ]
    if "heat_pump_air" in components:
        fields += [
            "heat_pump_heat_kwh",
            "heat_pump_electric_demand_kwh",
            "cost_heat_pump_eur",
            "emissions_heat_pump_kg",
        ]
    if "bess" in components:
        fields += ["bess_soc_kwh", "bess_soc_pct", "bess_charge_kwh", "bess_discharge_kwh", "cost_bess_eur"]
    if "tess" in components:
        fields += ["tess_soc_kwh", "tess_soc_pct", "tess_charge_kwh", "tess_discharge_kwh", "cost_tess_eur", "emissions_tess_kg"]
    return fields


def format_hourly_output_row(row: dict) -> dict:
    formatted_row: dict[str, object] = {}
    for key, value in row.items():
        if key == "timestamp":
            try:
                formatted_row[key] = datetime.fromisoformat(str(value)).strftime("%d.%m")
            except ValueError:
                formatted_row[key] = str(value)
        elif key == "hour":
            formatted_row[key] = f"{int(value):02d}:00"
        elif key == "season":
            continue
        else:
            formatted_row[key] = value
    return formatted_row


def write_hourly_results(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    formatted_rows = [format_hourly_output_row(row) for row in rows]
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(formatted_rows)


def build_annual_result_fields(components: dict) -> list[str]:
    fields = [
        "configuration",
        "configuration_label",
        "total_electricity_demand_kwh",
        "total_electricity_consumption_kwh",
        "total_thermal_demand_kwh",
        "annual_cost_grid_eur",
        "annual_cost_total_eur",
        "annual_emissions_grid_kg",
        "annual_emissions_total_kg",
    ]

    if "pv" in components:
        fields += [
            "total_pv_generation_kwh",
            "pv_self_consumption_fraction",
            "annual_cost_pv_capex_eur",
            "annual_cost_pv_om_eur",
            "annual_revenue_grid_eur",
        ]

    if "gas_boiler" in components:
        fields += ["annual_cost_gas_boiler_eur", "annual_emissions_gas_boiler_kg"]
    if "electric_boiler" in components:
        fields += ["annual_cost_electric_boiler_eur", "annual_emissions_electric_boiler_kg"]
    if "heat_pump_air" in components:
        fields += ["annual_cost_heat_pump_eur", "annual_emissions_heat_pump_kg"]
    if "bess" in components:
        fields += ["annual_cost_bess_eur", "annual_emissions_bess_kg"]
    if "tess" in components:
        fields += ["annual_cost_tess_eur", "annual_emissions_tess_kg"]
    return fields


def write_annual_results(path: Path, summary: dict, components: dict) -> None:
    fieldnames = build_annual_result_fields(components)
    filtered_summary = {field: summary.get(field, 0.0) for field in fieldnames}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerow(filtered_summary)


def remove_existing_output_files() -> None:
    figures_dir = BASE_DIR / "Results" / "Figures"
    tables_dir = BASE_DIR / "Results" / "Tables"
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    for pattern in ("*.pdf",):
        for fig_file in figures_dir.glob(pattern):
            try:
                os.remove(fig_file)
                print(f"  removed old figure: {fig_file}")
            except OSError as exc:
                print(f"  warning: could not remove {fig_file}: {exc}")

    for tbl_file in tables_dir.glob("*.csv"):
        try:
            os.remove(tbl_file)
            print(f"  removed old table: {tbl_file}")
        except OSError as exc:
            print(f"  warning: could not remove {tbl_file}: {exc}")


def plot_example_energy_diagrams(hourly_results: list[dict], components: dict, config_name: str, label: str) -> None:
    bar_width = 0.6
    hours = np.array([r["hour"] for r in hourly_results], dtype=float)
    config_label = CONFIG_LABELS.get(config_name, config_name)

    elec_line_cols = ["grid_supply_kwh", "grid_export_kwh"]
    if "pv" in components:
        elec_line_cols.append("pv_output_kwh")
    if "heat_pump_air" in components:
        elec_line_cols.append("heat_pump_electric_demand_kwh")
    if "electric_boiler" in components:
        elec_line_cols.append("electric_boiler_electric_demand_kwh")
    if "bess" in components:
        elec_line_cols.append("bess_charge_kwh")
        elec_line_cols.append("bess_discharge_kwh")

    therm_line_cols: list[str] = []
    if "heat_pump_air" in components:
        therm_line_cols.append("heat_pump_heat_kwh")
    if "gas_boiler" in components:
        therm_line_cols.append("gas_boiler_heat_kwh")
    if "electric_boiler" in components:
        therm_line_cols.append("electric_boiler_heat_kwh")
    if "tess" in components:
        therm_line_cols.append("tess_charge_kwh")
        therm_line_cols.append("tess_discharge_kwh")

    legend_labels = {
        "electricity_demand_kwh": "Elec. demand",
        "total_electricity_consumption_kwh": "Total elec. (additional)",
        "pv_output_kwh": "PV output",
        "grid_supply_kwh": "Grid import",
        "grid_export_kwh": "Grid export",
        "heat_pump_electric_demand_kwh": "HP elec.",
        "electric_boiler_electric_demand_kwh": "EB elec.",
        "bess_charge_kwh": "BESS charge",
        "bess_discharge_kwh": "BESS discharge",
        "thermal_demand_kwh": "Thermal demand",
        "heat_pump_heat_kwh": "HP heat",
        "gas_boiler_heat_kwh": "Gas boiler",
        "electric_boiler_heat_kwh": "EB heat",
        "tess_charge_kwh": "TESS charge",
        "tess_discharge_kwh": "TESS discharge",
    }

    bar_colors = {
        "electricity_demand_kwh": "#1f77b4",
        "total_electricity_consumption_kwh": "#ff7f0e",
        "thermal_demand_kwh": "#8c564b",
    }

    line_colors = {
        "pv_output_kwh": "#f7c948",
        "grid_supply_kwh": "#17becf",
        "grid_export_kwh": "#aec7e8",
        "heat_pump_electric_demand_kwh": "#2ca02c",
        "electric_boiler_electric_demand_kwh": "#d62728",
        "bess_charge_kwh": "#9467bd",
        "bess_discharge_kwh": "#c5b0d5",
        "heat_pump_heat_kwh": "#e377c2",
        "gas_boiler_heat_kwh": "#7f7f7f",
        "electric_boiler_heat_kwh": "#bcbd22",
        "tess_charge_kwh": "#17becf",
        "tess_discharge_kwh": "#9edae5",
    }

    line_styles = {
        "pv_output_kwh": "-",
        "grid_supply_kwh": "--",
        "grid_export_kwh": "-.",
        "heat_pump_electric_demand_kwh": "-",
        "electric_boiler_electric_demand_kwh": "--",
        "bess_charge_kwh": "-",
        "bess_discharge_kwh": "--",
        "heat_pump_heat_kwh": "-",
        "gas_boiler_heat_kwh": "--",
        "electric_boiler_heat_kwh": "-.",
        "tess_charge_kwh": "-",
        "tess_discharge_kwh": "--",
    }

    fig, ax = plt.subplots(figsize=(10, 6))
    elec_demand = np.array([r["electricity_demand_kwh"] for r in hourly_results])
    total_elec = np.array([r["total_electricity_consumption_kwh"] for r in hourly_results])
    extra_elec = np.maximum(0.0, total_elec - elec_demand)

    ax.bar(hours, elec_demand, width=bar_width, color=bar_colors["electricity_demand_kwh"], label=legend_labels["electricity_demand_kwh"], zorder=2)
    ax.bar(hours, extra_elec, width=bar_width, bottom=elec_demand, color=bar_colors["total_electricity_consumption_kwh"], label=legend_labels["total_electricity_consumption_kwh"], zorder=2)

    for col in elec_line_cols:
        values = -np.array([r[col] for r in hourly_results]) if col == "bess_discharge_kwh" else np.array([r[col] for r in hourly_results])
        ax.plot(hours, values, label=legend_labels[col], color=line_colors[col], linestyle=line_styles[col], linewidth=2, zorder=3)

    ax.set_title(f"{config_label} | {label} | Electrical Energy")
    ax.set_xlabel("Hour of day [h]")
    ax.set_ylabel("Electrical energy [kWh]")
    ax.set_xlim(-0.5, 23.5)
    ax.set_ylim(-(ELECTRICAL_Y_MAX * 0.25), ELECTRICAL_Y_MAX)
    ax.set_xticks(range(0, 24))
    ax.set_yticks(np.arange(-(ELECTRICAL_Y_MAX * 0.25), ELECTRICAL_Y_MAX + 0.1, 1.0))
    ax.axhline(0, color="black", linewidth=0.8, linestyle="-")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="upper left", fontsize=10)
    el_output = BASE_DIR / "Results" / "Figures" / f"{config_name}_{label}_el.pdf"
    fig.tight_layout()
    fig.savefig(el_output, bbox_inches="tight")
    plt.close(fig)
    print(f"  diagram saved: {el_output}")

    fig, ax = plt.subplots(figsize=(10, 6))
    thermal_demand = np.array([r["thermal_demand_kwh"] for r in hourly_results])
    ax.bar(hours, thermal_demand, width=bar_width, color=bar_colors["thermal_demand_kwh"], label=legend_labels["thermal_demand_kwh"], zorder=2)

    for col in therm_line_cols:
        values = -np.array([r[col] for r in hourly_results]) if col == "tess_discharge_kwh" else np.array([r[col] for r in hourly_results])
        ax.plot(hours, values, label=legend_labels[col], color=line_colors[col], linestyle=line_styles[col], linewidth=2, zorder=3)

    ax.set_title(f"{config_label} | {label} | Thermal Energy")
    ax.set_xlabel("Hour of day [h]")
    ax.set_ylabel("Thermal energy [kWh]")
    ax.set_xlim(-0.5, 23.5)
    ax.set_ylim(-4.0, 12.5)
    ax.set_xticks(range(0, 24))
    ax.set_yticks(np.arange(-4.0, 12.6, 2.0))
    ax.axhline(0, color="black", linewidth=0.8, linestyle="-")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="upper left", fontsize=10)
    th_output = BASE_DIR / "Results" / "Figures" / f"{config_name}_{label}_th.pdf"
    fig.tight_layout()
    fig.savefig(th_output, bbox_inches="tight")
    plt.close(fig)
    print(f"  diagram saved: {th_output}")


def plot_example_soc_diagram(hourly_results: list[dict], components: dict, config_name: str, label: str) -> None:
    has_bess = "bess" in components
    has_tess = "tess" in components
    if not has_bess and not has_tess:
        return

    hours = np.array([r["hour"] for r in hourly_results], dtype=float)
    config_label = CONFIG_LABELS.get(config_name, config_name)
    bar_width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))
    if has_bess and has_tess:
        offset = bar_width / 2.0
        ax.bar(hours - offset, [r["bess_soc_pct"] for r in hourly_results], width=bar_width, color="#9467bd", label="BESS SOC", zorder=2)
        ax.bar(hours + offset, [r["tess_soc_pct"] for r in hourly_results], width=bar_width, color="#17becf", label="TESS SOC", zorder=2)
    elif has_bess:
        ax.bar(hours, [r["bess_soc_pct"] for r in hourly_results], width=bar_width * 1.5, color="#9467bd", label="BESS SOC", zorder=2)
    else:
        ax.bar(hours, [r["tess_soc_pct"] for r in hourly_results], width=bar_width * 1.5, color="#17becf", label="TESS SOC", zorder=2)

    ax.set_title(f"{config_label} | {label} | Storage SOC")
    ax.set_xlabel("Hour of day [h]")
    ax.set_ylabel("State of Charge [%]")
    ax.set_xlim(-0.5, 23.5)
    ax.set_ylim(0, 100)
    ax.set_xticks(range(0, 24))
    ax.set_yticks(range(0, 101, 10))
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="upper left", fontsize=10)
    soc_output = BASE_DIR / "Results" / "Figures" / f"{config_name}_{label}_soc.pdf"
    fig.tight_layout()
    fig.savefig(soc_output, bbox_inches="tight")
    plt.close(fig)
    print(f"  diagram saved: {soc_output}")


def collect_annual_results() -> list[dict]:
    tables_dir = BASE_DIR / "Results" / "Tables"
    records = []
    files = sorted(tables_dir.glob("annual_results_*.csv"))
    if not files:
        raise FileNotFoundError(f"No annual_results_*.csv files found in {tables_dir}. Run simulation.py first.")

    for path in files:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                config_name = row.get("configuration", path.stem[len("annual_results_"):])
                records.append(
                    {
                        "config": config_name,
                        "configuration_label": row.get("configuration_label", CONFIG_LABELS.get(config_name, config_name)),
                        "annual_cost_total_eur": round(float(row.get("annual_cost_total_eur", 0.0)), 2),
                        "annual_emissions_total_kg": round(float(row.get("annual_emissions_total_kg", 0.0)), 2),
                    }
                )
    return records


def write_comparison_table(records: list[dict]) -> Path:
    tables_dir = BASE_DIR / "Results" / "Tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    out_path = tables_dir / "system_comparison.csv"
    fieldnames = ["config", "configuration_label", "annual_cost_total_eur", "annual_emissions_total_kg"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"  comparison table written to: {out_path}")
    return out_path


def plot_comparison_chart(records: list[dict]) -> Path:
    figures_dir = BASE_DIR / "Results" / "Figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    out_path = figures_dir / "system_comparison.pdf"

    labels = [r["configuration_label"] for r in records]
    costs = [r["annual_cost_total_eur"] for r in records]
    emissions = [r["annual_emissions_total_kg"] for r in records]

    x = np.arange(len(labels))
    bar_width = 0.6

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(max(12, len(labels) * 3.5), 6))
    bars1 = ax1.bar(x, costs, width=bar_width, color="#1f77b4", edgecolor="white", linewidth=0.6)
    ax1.set_title("Annual Total Cost")
    ax1.set_ylabel("Cost [EUR/year]")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=25, ha="right", fontsize=9)
    ax1.bar_label(bars1, fmt="%.0f", padding=3, fontsize=8)
    ax1.grid(axis="y", linestyle="--", alpha=0.4)
    ax1.set_axisbelow(True)

    bars2 = ax2.bar(x, emissions, width=bar_width, color="#2ca02c", edgecolor="white", linewidth=0.6)
    ax2.set_title("Annual Total Emissions")
    ax2.set_ylabel("Emissions [kg CO2eq/year]")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=25, ha="right", fontsize=9)
    ax2.bar_label(bars2, fmt="%.0f", padding=3, fontsize=8)
    ax2.grid(axis="y", linestyle="--", alpha=0.4)
    ax2.set_axisbelow(True)

    fig.suptitle("System Configuration Comparison", fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    print(f"  comparison chart saved to: {out_path}")
    return out_path


def run_comparison() -> None:
    records = collect_annual_results()
    write_comparison_table(records)
    plot_comparison_chart(records)
    print(f"  {len(records)} configuration(s) compared.")


def get_example_start_index(series: list[tuple[datetime, ...]], month: int, day: int) -> int:
    for index, (timestamp, *_) in enumerate(series):
        if timestamp.month == month and timestamp.day == day:
            return index
    raise ValueError(f"No data found for {month:02d}-{day:02d}")


def run_period_simulation(
    components: dict,
    annualization_factor: float,
    electricity_series: list[tuple[datetime, float]],
    thermal_series: list[tuple[datetime, float]],
    solar_series: list[tuple[datetime, float, float]],
    start_index_electricity: int,
    start_index_thermal: int,
    start_index_solar: int,
    length: int,
    label: str | None = None,
 ) -> list[dict]:
    grid = components.get("grid")
    pv = components.get("pv")
    gas_boiler = components.get("gas_boiler")
    electric_boiler = components.get("electric_boiler")
    heat_pump_air = components.get("heat_pump_air")
    bess = components.get("bess")
    tess = components.get("tess")

    hourly_results: list[dict] = []

    if bess:
        bess.reset_soc()
    if tess:
        tess.reset_soc()

    for local_offset in range(length):
        elec_idx = start_index_electricity + local_offset
        thermal_idx = start_index_thermal + local_offset
        solar_idx = start_index_solar + local_offset
        hour_index = local_offset % 24
        day_index = (start_index_thermal // 24) + (local_offset // 24)

        electricity_timestamp, electricity_kwh = electricity_series[elec_idx]
        _, thermal_kwh = thermal_series[thermal_idx]
        _, irradiance, t_amb = solar_series[solar_idx]

        pv_output_kwh = 0.0
        pv_cell_temp_c = 0.0
        if pv:
            pv_output_kwh = pv.calc_pv_output_kwh(irradiance, t_amb)
            pv_cell_temp_c = pv.calc_pv_temperature(t_amb, irradiance)

        gas_boiler_heat_kwh = 0.0
        electric_boiler_heat_kwh = 0.0
        heat_pump_heat_kwh = 0.0
        heat_pump_electric_demand_kwh = 0.0
        electric_boiler_electric_demand_kwh = 0.0

        if heat_pump_air:
            heat_pump_heat_kwh = thermal_kwh
            heat_pump_electric_demand_kwh = heat_pump_air.get_electricity_demand_kwh(thermal_kwh, day_index, hour_index)
        elif electric_boiler and not gas_boiler:
            electric_boiler_heat_kwh = thermal_kwh
        elif gas_boiler and not electric_boiler:
            gas_boiler_heat_kwh = thermal_kwh
        elif gas_boiler and electric_boiler:
            electric_boiler_heat_kwh = thermal_kwh

        if tess:
            tess_discharge_kwh = tess.get_discharge_for_demand(thermal_kwh)
            tess_heat_supplied = tess.get_heat_from_discharge(tess_discharge_kwh)
            remaining_thermal_demand = max(0.0, thermal_kwh - tess_heat_supplied)
        else:
            tess_discharge_kwh = 0.0
            tess_heat_supplied = 0.0
            remaining_thermal_demand = thermal_kwh

        if heat_pump_air:
            heat_pump_heat_kwh = remaining_thermal_demand
        elif electric_boiler and not gas_boiler:
            electric_boiler_heat_kwh = remaining_thermal_demand
        elif gas_boiler and not electric_boiler:
            gas_boiler_heat_kwh = remaining_thermal_demand
        elif gas_boiler and electric_boiler:
            electric_boiler_heat_kwh = remaining_thermal_demand

        tess_charge_kwh = 0.0
        if tess and tess.available_charge_capacity_kwh() > 0.0:
            tess_charge_kwh = tess.get_charge_from_heat_source(heat_pump_heat_kwh + electric_boiler_heat_kwh + gas_boiler_heat_kwh)
            if tess_charge_kwh > 0.0:
                if heat_pump_air:
                    heat_pump_heat_kwh += tess_charge_kwh
                elif electric_boiler and not gas_boiler:
                    electric_boiler_heat_kwh += tess_charge_kwh
                elif gas_boiler and not electric_boiler:
                    gas_boiler_heat_kwh += tess_charge_kwh
                elif gas_boiler and electric_boiler:
                    electric_boiler_heat_kwh += tess_charge_kwh

        if electric_boiler and electric_boiler_heat_kwh > 0:
            electric_boiler_electric_demand_kwh = electric_boiler.get_electricity_demand_kwh(electric_boiler_heat_kwh)

        if heat_pump_air:
            heat_pump_electric_demand_kwh = heat_pump_air.get_electricity_demand_kwh(heat_pump_heat_kwh, day_index, hour_index)

        if tess:
            tess.update_state(q_tess_in=tess_charge_kwh, q_tess_out=tess_discharge_kwh)
            tess_soc_kwh = tess.soc
            tess_soc_pct = tess.soc_pct
        else:
            tess_soc_kwh = 0.0
            tess_soc_pct = 0.0

        heat_source_electricity_demand_kwh = electric_boiler_electric_demand_kwh + heat_pump_electric_demand_kwh
        total_electricity_consumption_kwh = electricity_kwh + heat_source_electricity_demand_kwh
        bess_charge_kwh = 0.0
        bess_discharge_kwh = 0.0
        if bess:
            if hour_index == 0:
                bess.reset_soc()
            if pv_output_kwh > total_electricity_consumption_kwh:
                surplus = pv_output_kwh - total_electricity_consumption_kwh
                max_charge_kwh = min(surplus, bess.P_max, bess.available_charge_capacity_kwh() / bess.eta_char)
                bess_charge_kwh = max(0.0, max_charge_kwh)
                bess.apply_self_discharge()
                bess.soc += bess.get_charge_energy_input(bess_charge_kwh)
            elif pv_output_kwh < total_electricity_consumption_kwh:
                deficit = total_electricity_consumption_kwh - pv_output_kwh
                max_discharge_kwh = min(deficit, bess.P_max, bess.available_discharge_capacity_kwh() * bess.eta_disc)
                bess_discharge_kwh = max(0.0, max_discharge_kwh)
                bess.apply_self_discharge()
                bess.soc -= bess.get_discharge_energy_output(bess_discharge_kwh)
            else:
                bess.apply_self_discharge()

            bess.clamp_soc()
            grid_supply_kwh = max(0.0, total_electricity_consumption_kwh - pv_output_kwh - bess_discharge_kwh)
            grid_cost_supply_kwh = max(0.0, electricity_kwh - pv_output_kwh - bess_discharge_kwh)
            grid_export_kwh = max(0.0, pv_output_kwh - total_electricity_consumption_kwh - bess_charge_kwh)
        else:
            grid_supply_kwh = max(0.0, total_electricity_consumption_kwh - pv_output_kwh)
            grid_cost_supply_kwh = max(0.0, electricity_kwh - pv_output_kwh)
            grid_export_kwh = max(0.0, pv_output_kwh - total_electricity_consumption_kwh)

        bess_soc_kwh = bess.soc if bess else 0.0
        bess_soc_pct = bess.soc_pct if bess else 0.0

        if hour_index == 23:
            if bess:
                bess_delta_kwh = bess.force_soc_to_target()
                if bess_delta_kwh > 0.0:
                    grid_supply_kwh += bess_delta_kwh
                    total_electricity_consumption_kwh += bess_delta_kwh
                elif bess_delta_kwh < 0.0:
                    grid_export_kwh += abs(bess_delta_kwh)
                bess_soc_kwh = bess.soc
                bess_soc_pct = bess.soc_pct

            if tess:
                tess_delta_kwh = tess.force_soc_to_target()
                if tess_delta_kwh > 0.0:
                    thermal_kwh += tess_delta_kwh
                    if heat_pump_air:
                        heat_pump_heat_kwh += tess_delta_kwh
                        heat_pump_electric_demand_kwh = heat_pump_air.get_electricity_demand_kwh(heat_pump_heat_kwh, day_index, hour_index)
                        total_electricity_consumption_kwh += heat_pump_air.get_electricity_demand_kwh(tess_delta_kwh, day_index, hour_index)
                    elif electric_boiler and not gas_boiler:
                        electric_boiler_heat_kwh += tess_delta_kwh
                        extra_elec = electric_boiler.get_electricity_demand_kwh(tess_delta_kwh)
                        electric_boiler_electric_demand_kwh += extra_elec
                        total_electricity_consumption_kwh += extra_elec
                    elif gas_boiler:
                        gas_boiler_heat_kwh += tess_delta_kwh
                tess_soc_kwh = tess.soc
                tess_soc_pct = tess.soc_pct

        cost_pv_capex_hour_eur = 0.0
        cost_pv_om_eur = 0.0
        if pv:
            cost_pv_capex_hour_eur = pv.get_capex_hour_eur(annualization_factor)
            cost_pv_om_eur = pv.get_om_cost_eur(pv_output_kwh)

        cost_grid_eur = 0.0
        cost_grid_subscription_eur = 0.0
        grid_revenue_eur = 0.0
        if grid:
            cost_grid_eur = grid.get_cost_eur(grid_cost_supply_kwh)
            cost_grid_subscription_eur = grid.get_subscription_cost_hour_eur(annualization_factor)
            grid_revenue_eur = grid.get_revenue_eur(grid_export_kwh)

        cost_gas_boiler_eur = 0.0
        if gas_boiler:
            cost_gas_boiler_eur = gas_boiler.get_cost_eur(gas_boiler_heat_kwh)

        cost_electric_boiler_eur = 0.0
        if electric_boiler:
            cost_electric_boiler_eur = electric_boiler.get_cost_eur(electric_boiler_heat_kwh)

        cost_heat_pump_eur = 0.0
        if heat_pump_air:
            cost_heat_pump_eur = heat_pump_air.get_cost_eur(heat_pump_heat_kwh)

        cost_bess_eur = 0.0
        if bess:
            cost_bess_eur = bess.get_cost_eur(bess_discharge_kwh)

        cost_tess_eur = 0.0
        if tess:
            cost_tess_eur = tess.get_cost_eur(tess_discharge_kwh)

        total_cost_hour_eur = (
            cost_pv_capex_hour_eur + cost_pv_om_eur + cost_grid_eur + cost_grid_subscription_eur - grid_revenue_eur + cost_gas_boiler_eur + cost_electric_boiler_eur + cost_heat_pump_eur + cost_bess_eur + cost_tess_eur
        )

        emissions_grid_kg = grid.get_emissions_kg(grid_supply_kwh) if grid else 0.0
        emissions_gas_boiler_kg = gas_boiler.get_emissions_kg(gas_boiler_heat_kwh) if gas_boiler else 0.0
        emissions_electric_boiler_kg = electric_boiler.get_emissions_kg(electric_boiler_heat_kwh) if electric_boiler else 0.0
        emissions_heat_pump_kg = heat_pump_air.get_emissions_kg(heat_pump_heat_kwh) if heat_pump_air else 0.0
        emissions_bess_kg = bess.get_emissions_kg(bess_discharge_kwh) if bess else 0.0
        emissions_tess_kg = tess.get_emissions_kg(tess_discharge_kwh) if tess else 0.0
        total_emissions_hour_kg = emissions_grid_kg + emissions_gas_boiler_kg + emissions_electric_boiler_kg + emissions_heat_pump_kg + emissions_bess_kg + emissions_tess_kg

        hourly_results.append(
            {
                "timestamp": electricity_timestamp.isoformat(),
                "season": label or "",
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
                "bess_soc_pct": round(bess_soc_pct, 2),
                "bess_charge_kwh": round(bess_charge_kwh, 4),
                "bess_discharge_kwh": round(bess_discharge_kwh, 4),
                "tess_soc_kwh": round(tess_soc_kwh, 4),
                "tess_soc_pct": round(tess_soc_pct, 2),
                "tess_charge_kwh": round(tess_charge_kwh, 4),
                "tess_discharge_kwh": round(tess_discharge_kwh, 4),
                "cost_pv_capex_hour_eur": round(cost_pv_capex_hour_eur, 4),
                "cost_pv_om_eur": round(cost_pv_om_eur, 4),
                "cost_grid_eur": round(cost_grid_eur, 4),
                "cost_grid_subscription_eur": round(cost_grid_subscription_eur, 4),
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

    return hourly_results


def evaluate_configuration_full_year(
    component_config: dict,
    electricity_series: list[tuple[datetime, float]],
    thermal_series: list[tuple[datetime, float]],
    solar_series: list[tuple[datetime, float, float]],
    heat_pump_cop_series: list[list[float]],
) -> dict:
    components = apply_component_parameters(component_config, heat_pump_cop_series=heat_pump_cop_series)
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

    total_electricity_demand_kwh = sum(r.get("electricity_demand_kwh", 0.0) for r in full_year_results)
    total_electricity_consumption_kwh = sum(r.get("total_electricity_consumption_kwh", 0.0) for r in full_year_results)
    total_thermal_demand_kwh = sum(r.get("thermal_demand_kwh", 0.0) for r in full_year_results)
    total_pv_generation_kwh = sum(r.get("pv_output_kwh", 0.0) for r in full_year_results)
    total_pv_used_kwh = sum(max(0.0, r.get("pv_output_kwh", 0.0) - r.get("grid_export_kwh", 0.0)) for r in full_year_results)
    annual_cost_pv_capex_eur = sum(r.get("cost_pv_capex_hour_eur", 0.0) for r in full_year_results)
    annual_cost_pv_om_eur = sum(r.get("cost_pv_om_eur", 0.0) for r in full_year_results)
    annual_cost_grid_eur = sum(r.get("cost_grid_eur", 0.0) for r in full_year_results)
    annual_cost_gas_boiler_eur = sum(r.get("cost_gas_boiler_eur", 0.0) for r in full_year_results)
    annual_cost_electric_boiler_eur = sum(r.get("cost_electric_boiler_eur", 0.0) for r in full_year_results)
    annual_cost_heat_pump_eur = sum(r.get("cost_heat_pump_eur", 0.0) for r in full_year_results)
    annual_cost_bess_eur = sum(r.get("cost_bess_eur", 0.0) for r in full_year_results)
    annual_cost_tess_eur = sum(r.get("cost_tess_eur", 0.0) for r in full_year_results)
    annual_revenue_grid_eur = sum(r.get("grid_revenue_eur", 0.0) for r in full_year_results)
    annual_cost_total_eur = (
        annual_cost_pv_capex_eur
        + annual_cost_pv_om_eur
        + annual_cost_grid_eur
        - annual_revenue_grid_eur
        + annual_cost_gas_boiler_eur
        + annual_cost_electric_boiler_eur
        + annual_cost_heat_pump_eur
        + annual_cost_bess_eur
        + annual_cost_tess_eur
    )
    annual_emissions_grid_kg = sum(r.get("emissions_grid_kg", 0.0) for r in full_year_results)
    annual_emissions_gas_boiler_kg = sum(r.get("emissions_gas_boiler_kg", 0.0) for r in full_year_results)
    annual_emissions_electric_boiler_kg = sum(r.get("emissions_electric_boiler_kg", 0.0) for r in full_year_results)
    annual_emissions_heat_pump_kg = sum(r.get("emissions_heat_pump_kg", 0.0) for r in full_year_results)
    annual_emissions_bess_kg = sum(r.get("emissions_bess_kg", 0.0) for r in full_year_results)
    annual_emissions_tess_kg = sum(r.get("emissions_tess_kg", 0.0) for r in full_year_results)
    annual_emissions_total_kg = (
        annual_emissions_grid_kg
        + annual_emissions_gas_boiler_kg
        + annual_emissions_electric_boiler_kg
        + annual_emissions_heat_pump_kg
        + annual_emissions_bess_kg
        + annual_emissions_tess_kg
    )

    return {
        "components": components,
        "full_year_results": full_year_results,
        "total_electricity_demand_kwh": total_electricity_demand_kwh,
        "total_electricity_consumption_kwh": total_electricity_consumption_kwh,
        "total_thermal_demand_kwh": total_thermal_demand_kwh,
        "total_pv_generation_kwh": total_pv_generation_kwh,
        "total_pv_used_kwh": total_pv_used_kwh,
        "annual_cost_pv_capex_eur": annual_cost_pv_capex_eur,
        "annual_cost_pv_om_eur": annual_cost_pv_om_eur,
        "annual_cost_grid_eur": annual_cost_grid_eur,
        "annual_cost_gas_boiler_eur": annual_cost_gas_boiler_eur,
        "annual_cost_electric_boiler_eur": annual_cost_electric_boiler_eur,
        "annual_cost_heat_pump_eur": annual_cost_heat_pump_eur,
        "annual_cost_bess_eur": annual_cost_bess_eur,
        "annual_cost_tess_eur": annual_cost_tess_eur,
        "annual_revenue_grid_eur": annual_revenue_grid_eur,
        "annual_cost_total_eur": annual_cost_total_eur,
        "annual_emissions_grid_kg": annual_emissions_grid_kg,
        "annual_emissions_gas_boiler_kg": annual_emissions_gas_boiler_kg,
        "annual_emissions_electric_boiler_kg": annual_emissions_electric_boiler_kg,
        "annual_emissions_heat_pump_kg": annual_emissions_heat_pump_kg,
        "annual_emissions_bess_kg": annual_emissions_bess_kg,
        "annual_emissions_tess_kg": annual_emissions_tess_kg,
        "annual_emissions_total_kg": annual_emissions_total_kg,
    }


def run_single_configuration(
    config_name: str,
    base_component_config: dict,
    electricity_series: list[tuple[datetime, float]],
    thermal_series: list[tuple[datetime, float]],
    solar_series: list[tuple[datetime, float, float]],
    heat_pump_cop_series: list[list[float]],
) -> None:
    component_config = apply_configuration(base_component_config, config_name)
    annualization_factor = component_config["annualization"]["factor"]
    evaluation_result = evaluate_configuration_full_year(
        component_config,
        electricity_series,
        thermal_series,
        solar_series,
        heat_pump_cop_series,
    )
    components = evaluation_result["components"]
    full_year_results = evaluation_result["full_year_results"]
    result_fields = build_result_fields(components)

    print(f"\n--- Configuration: {CONFIG_LABELS.get(config_name, config_name)} ---")

    total_electricity_demand = evaluation_result["total_electricity_demand_kwh"]
    total_electricity_consumption = evaluation_result["total_electricity_consumption_kwh"]
    total_thermal_demand = evaluation_result["total_thermal_demand_kwh"]
    total_pv_generation = evaluation_result["total_pv_generation_kwh"]
    total_pv_used = evaluation_result["total_pv_used_kwh"]
    annual_cost_pv_capex_total = evaluation_result["annual_cost_pv_capex_eur"]
    annual_cost_pv_om = evaluation_result["annual_cost_pv_om_eur"]
    annual_cost_grid = evaluation_result["annual_cost_grid_eur"]
    annual_revenue_grid = evaluation_result["annual_revenue_grid_eur"]
    annual_cost_gas_boiler = evaluation_result["annual_cost_gas_boiler_eur"]
    annual_cost_electric_boiler = evaluation_result["annual_cost_electric_boiler_eur"]
    annual_cost_heat_pump = evaluation_result["annual_cost_heat_pump_eur"]
    annual_cost_bess = evaluation_result["annual_cost_bess_eur"]
    annual_cost_tess = evaluation_result["annual_cost_tess_eur"]
    annual_cost_total = evaluation_result["annual_cost_total_eur"]
    annual_emissions_grid = evaluation_result["annual_emissions_grid_kg"]
    annual_emissions_gas_boiler = evaluation_result["annual_emissions_gas_boiler_kg"]
    annual_emissions_electric_boiler = evaluation_result["annual_emissions_electric_boiler_kg"]
    annual_emissions_heat_pump = evaluation_result["annual_emissions_heat_pump_kg"]
    annual_emissions_bess = evaluation_result["annual_emissions_bess_kg"]
    annual_emissions_tess = evaluation_result["annual_emissions_tess_kg"]
    annual_emissions_total = evaluation_result["annual_emissions_total_kg"]

    output_file = BASE_DIR / "Results" / "Tables" / f"hourly_results_{config_name}.csv"
    annual_output_file = BASE_DIR / "Results" / "Tables" / f"annual_results_{config_name}.csv"
    write_hourly_results(output_file, full_year_results, result_fields)
    write_annual_results(
        annual_output_file,
        {
            "configuration": config_name,
            "configuration_label": CONFIG_LABELS.get(config_name, config_name),
            "total_electricity_demand_kwh": round(total_electricity_demand, 4),
            "total_electricity_consumption_kwh": round(total_electricity_consumption, 4),
            "total_thermal_demand_kwh": round(total_thermal_demand, 4),
            "total_pv_generation_kwh": round(total_pv_generation, 4),
            "pv_self_consumption_fraction": round(total_pv_used / total_pv_generation if total_pv_generation > 0 else 0.0, 4),
            "annual_cost_pv_capex_eur": round(annual_cost_pv_capex_total, 4),
            "annual_cost_pv_om_eur": round(annual_cost_pv_om, 4),
            "annual_cost_grid_eur": round(annual_cost_grid, 4),
            "annual_cost_gas_boiler_eur": round(annual_cost_gas_boiler, 4),
            "annual_cost_electric_boiler_eur": round(annual_cost_electric_boiler, 4),
            "annual_cost_heat_pump_eur": round(annual_cost_heat_pump, 4),
            "annual_cost_bess_eur": round(annual_cost_bess, 4),
            "annual_cost_tess_eur": round(annual_cost_tess, 4),
            "annual_revenue_grid_eur": round(annual_revenue_grid, 4),
            "annual_cost_total_eur": round(annual_cost_total, 4),
            "annual_emissions_grid_kg": round(annual_emissions_grid, 4),
            "annual_emissions_gas_boiler_kg": round(annual_emissions_gas_boiler, 4),
            "annual_emissions_electric_boiler_kg": round(annual_emissions_electric_boiler, 4),
            "annual_emissions_heat_pump_kg": round(annual_emissions_heat_pump, 4),
            "annual_emissions_bess_kg": round(annual_emissions_bess, 4),
            "annual_emissions_tess_kg": round(annual_emissions_tess, 4),
            "annual_emissions_total_kg": round(annual_emissions_total, 4),
        },
        components,
    )

    print(f"  hourly results  -> {output_file}")
    print(f"  annual results  -> {annual_output_file}")

    for label, month, day in EXAMPLE_DATES:
        try:
            electricity_start = get_example_start_index(electricity_series, month, day)
            thermal_start = get_example_start_index(thermal_series, month, day)
            solar_start = get_example_start_index(solar_series, month, day)
            example_results = run_period_simulation(
                components,
                annualization_factor,
                electricity_series,
                thermal_series,
                solar_series,
                start_index_electricity=electricity_start,
                start_index_thermal=thermal_start,
                start_index_solar=solar_start,
                length=24,
                label=label,
            )
            write_hourly_results(BASE_DIR / "Results" / "Tables" / f"hourly_results_{config_name}_{label}.csv", example_results, result_fields)
            plot_example_energy_diagrams(example_results, components, config_name, label)
            plot_example_soc_diagram(example_results, components, config_name, label)
            print(f"  example results  -> {BASE_DIR / 'Results' / 'Tables' / f'hourly_results_{config_name}_{label}.csv'}")
        except ValueError as exc:
            print(f"  warning: could not generate example output for {label}: {exc}")


def main() -> None:
    base_component_config = load_component_parameters(COMPONENT_PARAMETERS_FILE)
    ups = base_component_config["neighborhood_upscaling"]
    N_HOUSEHOLDS      = int(ups["n_households"])
    SIGMA_LOG_ELEC    = float(ups["sigma_log_electricity"])
    SIGMA_LOG_THERM   = float(ups["sigma_log_thermal"])
    COINCIDENCE_ALPHA = float(ups["coincidence_alpha"])
    SEED_OFFSET_ELEC  = int(ups["seed_offset_electricity"])
    SEED_OFFSET_THERM = int(ups["seed_offset_thermal"])
    if not SOLAR_DATA_FILE.exists():
        raise FileNotFoundError(f"Solar data file not found: {SOLAR_DATA_FILE}")

    electricity_series = read_electricity_demand(ELECTRICITY_DATA_FILE)
    thermal_series = read_thermal_demand(THERMAL_DATA_FILE)
    solar_series = read_solar_data(SOLAR_DATA_FILE)
    heat_pump_cop_series = load_heat_pump_cop_series(THERMAL_DATA_FILE)

    electricity_series = upscale_demand_series(
        electricity_series,
        n_households=N_HOUSEHOLDS,
        sigma_log=SIGMA_LOG_ELEC,
        coincidence_alpha=COINCIDENCE_ALPHA,
        seed=N_HOUSEHOLDS + SEED_OFFSET_ELEC,
    )
    thermal_series = upscale_demand_series(
        thermal_series,
        n_households=N_HOUSEHOLDS,
        sigma_log=SIGMA_LOG_THERM,
        coincidence_alpha=COINCIDENCE_ALPHA,
        seed=N_HOUSEHOLDS + SEED_OFFSET_THERM,
    )

    if len(electricity_series) == 0 or len(thermal_series) == 0 or len(solar_series) == 0:
        raise ValueError("At least one input series is empty")

    remove_existing_output_files()

    for config_name in CONFIGURATIONS:
        run_single_configuration(config_name, copy.deepcopy(base_component_config), electricity_series, thermal_series, solar_series, heat_pump_cop_series)

    print("\n--- Running cross-configuration comparison ---")
    run_comparison()
    print("\nAll configurations and comparison completed.")


if __name__ == "__main__":
    main()
