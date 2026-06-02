# Scenario: PV + utility grid + gas boiler
from pathlib import Path
import csv

# Utility Grid Parameters
ELECTRICITY_PRICE_EUR_PER_KWH = 0.1793
UTILITY_GRID_EMISSION_FACTOR_KG_PER_KWH = 0.020

# Gas boiler Parameters
GAS_BOILER_LCOH_EUR_PER_KWH = 0.13
GAS_BOILER_EMISSION_FACTOR_KG_PER_KWH = 0.02

# PV System Parameters
I_STC = 1000.0          # W/m², STC irradiance
T_STC = 25.0            # °C, STC cell temperature
I_REF = 800.0           # W/m², reference irradiance for temperature model
T_REF = 20.0            # °C, reference ambient temperature
T_NOM = 44.0            # °C, Nominal Module Operating Temperature (NOCT)
BETA = 0.0024           # per °C, temperature coefficient (0.24 %/°C → 0.0024 /°C)
A_PVP = 2.08            # m², area per panel
N_PVH = 8               # number of panels per household (6 panels equals about 2820 Wp)
P_PV_RHO = 224          # W/m², Power density PV panel
C_CAP_PVP = 15.74       # €/year, annualized capital cost per panel including interest 
C_OM_PV = 0.01          # €/kWh, operation & maintenance cost per kWh generated

# Derived PV constants
P_PV_PEAK = P_PV_RHO * A_PVP * N_PVH / 1000.0  # kWp installed peak power
C_CAP_TOTAL = C_CAP_PVP * N_PVH                # €/year, total annualized capital cost

ANNUALIZATION_FACTOR = 91.25  # 4 * 91.25 = 365 days

# File paths and column names
BASE_DIR = Path(__file__).resolve().parent.parent
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

OUTPUT_FILE = BASE_DIR / "Results" / "hourly_results_pv_grid_gas.csv"
ELECTRICITY_COLUMN_NAME = "Median"
THERMAL_SPACE_COLUMN = "FR_heat_demand_space_SFH"
THERMAL_WATER_COLUMN = "FR_heat_demand_water"

# Output CSV columns
RESULT_FIELDS = [
    "season",
    "hour",
    "electricity_demand_kwh",
    "thermal_demand_kwh",
    "pv_output_kwh",
    "pv_curtailed_kwh",
    "pv_cell_temp_c",
    "grid_supply_kwh",
    "gas_boiler_heat_kwh",
    "cost_pv_om_eur",
    "cost_grid_eur",
    "cost_gas_boiler_eur",
    "emissions_grid_kg",
    "emissions_gas_boiler_kg",
    "total_cost_hour_eur",
    "total_emissions_hour_kg",
]


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


def calc_pv_temperature(T_amb: float, irradiance: float) -> float:
    # Compute PV cell temperature from ambient temperature and irradiance.
    return T_amb + (T_NOM - T_REF) * (irradiance / I_REF)


def calc_pv_output_kwh(irradiance: float, T_amb: float) -> float:
    # Compute PV output in kWh for one hour with temperature derating.
    T_pv = calc_pv_temperature(T_amb, irradiance)
    P_pv_w = P_PV_PEAK * 1000 * (irradiance / I_STC) * (1.0 - BETA * (T_pv - T_STC))
    P_pv_w = max(0.0, P_pv_w)
    return P_pv_w / 1000.0


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
        "total_thermal_demand_kwh",
        "total_pv_generation_kwh",
        "total_pv_curtailed_kwh",
        "pv_self_consumption_fraction",
        "annual_cost_pv_capex_eur",
        "annual_cost_pv_om_eur",
        "annual_cost_grid_eur",
        "annual_cost_gas_boiler_eur",
        "annual_cost_total_eur",
        "annual_emissions_grid_kg",
        "annual_emissions_gas_boiler_kg",
        "annual_emissions_total_kg",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(summary)


def main() -> None:
    # Read data, compute hourly results, and write outputs.
    hourly_results = []
    total_electricity_demand = 0.0
    total_thermal_demand = 0.0
    total_pv_generation = 0.0
    total_pv_curtailed = 0.0
    total_pv_used = 0.0
    total_cost_pv_om = 0.0
    total_cost_grid = 0.0
    total_cost_gas_boiler = 0.0
    total_emissions_grid = 0.0
    total_emissions_gas_boiler = 0.0

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

            # Calculate PV output
            pv_output_kwh = calc_pv_output_kwh(irradiance, T_amb)
            pv_cell_temp_c = calc_pv_temperature(T_amb, irradiance)


            # Electricity Energy balance
            # Dispatch: PV covers demand first, grid covers residual
            grid_supply_kwh = max(0.0, electricity_kwh - pv_output_kwh)
            pv_curtailed_kwh = max(0.0, pv_output_kwh - electricity_kwh)
            pv_used_kwh = pv_output_kwh - pv_curtailed_kwh


            # Thermal Energy balance
            # Gas boiler covers all thermal demand for now
            gas_boiler_heat_kwh = thermal_kwh

            # Costs
            cost_pv_capex_hour_eur = C_CAP_TOTAL / (365.0 * 24.0)  # Annualized, hourly allocation; will change later to different approach
            cost_pv_om_eur = pv_output_kwh * C_OM_PV
            cost_grid_eur = grid_supply_kwh * ELECTRICITY_PRICE_EUR_PER_KWH
            cost_gas_boiler_eur = gas_boiler_heat_kwh * GAS_BOILER_LCOH_EUR_PER_KWH
        

            total_cost_hour_eur = (
                cost_pv_capex_hour_eur
                + cost_pv_om_eur
                + cost_grid_eur
                + cost_gas_boiler_eur
            )

            # Emissions (PV has zero direct emissions)
            emissions_grid_kg = grid_supply_kwh * UTILITY_GRID_EMISSION_FACTOR_KG_PER_KWH
            emissions_gas_boiler_kg = gas_boiler_heat_kwh * GAS_BOILER_EMISSION_FACTOR_KG_PER_KWH
            total_emissions_hour_kg = emissions_grid_kg + emissions_gas_boiler_kg

            # Accumulate annual totals
            total_electricity_demand += electricity_kwh
            total_thermal_demand += thermal_kwh
            total_pv_generation += pv_output_kwh
            total_pv_curtailed += pv_curtailed_kwh
            total_pv_used += pv_used_kwh
            total_cost_pv_om += cost_pv_om_eur
            total_cost_grid += cost_grid_eur
            total_cost_gas_boiler += cost_gas_boiler_eur
            total_emissions_grid += emissions_grid_kg
            total_emissions_gas_boiler += emissions_gas_boiler_kg

            hourly_results.append(
                {
                    "season": season_name,
                    "hour": hour_index,
                    "electricity_demand_kwh": round(electricity_kwh, 4),
                    "thermal_demand_kwh": round(thermal_kwh, 4),
                    "pv_output_kwh": round(pv_output_kwh, 4),
                    "pv_curtailed_kwh": round(pv_curtailed_kwh, 4),
                    "pv_cell_temp_c": round(pv_cell_temp_c, 2),
                    "grid_supply_kwh": round(grid_supply_kwh, 4),
                    "gas_boiler_heat_kwh": round(gas_boiler_heat_kwh, 4),
                    "cost_pv_om_eur": round(cost_pv_om_eur, 4),
                    "cost_grid_eur": round(cost_grid_eur, 4),
                    "cost_gas_boiler_eur": round(cost_gas_boiler_eur, 4),
                    "emissions_grid_kg": round(emissions_grid_kg, 4),
                    "emissions_gas_boiler_kg": round(emissions_gas_boiler_kg, 4),
                    "total_cost_hour_eur": round(total_cost_hour_eur, 4),
                    "total_emissions_hour_kg": round(total_emissions_hour_kg, 4),
                }
            )

    # Write hourly results
    write_hourly_results(OUTPUT_FILE, hourly_results)

    # Calculate annual aggregates
    annual_electricity_demand = total_electricity_demand * ANNUALIZATION_FACTOR
    annual_thermal_demand = total_thermal_demand * ANNUALIZATION_FACTOR
    annual_pv_generation = total_pv_generation * ANNUALIZATION_FACTOR
    annual_pv_curtailed = total_pv_curtailed * ANNUALIZATION_FACTOR
    pv_self_consumption_fraction = (
        total_pv_used / total_pv_generation if total_pv_generation > 0 else 0.0
    )

    annual_cost_pv_capex = C_CAP_TOTAL
    annual_cost_pv_om = total_cost_pv_om * ANNUALIZATION_FACTOR
    annual_cost_grid = total_cost_grid * ANNUALIZATION_FACTOR
    annual_cost_gas_boiler = total_cost_gas_boiler * ANNUALIZATION_FACTOR
    annual_cost_total = (
        annual_cost_pv_capex
        + annual_cost_pv_om
        + annual_cost_grid
        + annual_cost_gas_boiler
    )

    annual_emissions_grid = total_emissions_grid * ANNUALIZATION_FACTOR
    annual_emissions_gas_boiler = total_emissions_gas_boiler * ANNUALIZATION_FACTOR
    annual_emissions_total = annual_emissions_grid + annual_emissions_gas_boiler

    annual_output_file = BASE_DIR / "Results" / "annual_results_pv_grid_gas.csv"
    write_annual_results(
        annual_output_file,
        {
            "total_electricity_demand_kwh": round(annual_electricity_demand, 4),
            "total_thermal_demand_kwh": round(annual_thermal_demand, 4),
            "total_pv_generation_kwh": round(annual_pv_generation, 4),
            "total_pv_curtailed_kwh": round(annual_pv_curtailed, 4),
            "pv_self_consumption_fraction": round(pv_self_consumption_fraction, 4),
            "annual_cost_pv_capex_eur": round(annual_cost_pv_capex, 4),
            "annual_cost_pv_om_eur": round(annual_cost_pv_om, 4),
            "annual_cost_grid_eur": round(annual_cost_grid, 4),
            "annual_cost_gas_boiler_eur": round(annual_cost_gas_boiler, 4),
            "annual_cost_total_eur": round(annual_cost_total, 4),
            "annual_emissions_grid_kg": round(annual_emissions_grid, 4),
            "annual_emissions_gas_boiler_kg": round(annual_emissions_gas_boiler, 4),
            "annual_emissions_total_kg": round(annual_emissions_total, 4),
        },
    )

    print(f"  hourly results written to: {OUTPUT_FILE}")
    print(f"  annual results written to: {annual_output_file}")
if __name__ == "__main__":
    main()
