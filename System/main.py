from pathlib import Path
import csv

# Constants for scenario 1: utility grid electricity + gas boiler thermal supply
ELECTRICITY_PRICE_EUR_PER_KWH = 0.1793
GAS_BOILER_LCOH_EUR_PER_KWH = 0.13
GAS_BOILER_EMISSION_FACTOR_KG_PER_KWH = 0.02
UTILITY_GRID_EMISSION_FACTOR_KG_PER_KWH = 0.052
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
OUTPUT_FILE = BASE_DIR / "results" / "hourly_results_base.csv"
ELECTRICITY_COLUMN_NAME = "Mean"
THERMAL_SPACE_COLUMN = "FR_heat_demand_space_SFH"
THERMAL_WATER_COLUMN = "FR_heat_demand_water"

# Output CSV columns
RESULT_FIELDS = [
    "season",
    "hour",
    "electricity_demand_kwh",
    "thermal_demand_kwh",
    "utility_grid_supply_kwh",
    "gas_boiler_heat_kwh",
    "cost_utility_grid_eur",
    "cost_gas_boiler_eur",
    "emissions_utility_grid_kg",
    "emissions_gas_boiler_kg",
    "total_cost_hour_eur",
    "total_emissions_hour_kg",
]


def parse_float(value):
    """Convert a CSV string to float, handling common decimal formats."""
    if value is None:
        return 0.0
    return float(value.replace(",", "."))


def read_electricity_demand(path):
    """Read hourly electricity demand from the CSV file."""
    values = []
    with path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            demand = parse_float(row[ELECTRICITY_COLUMN_NAME])
            values.append(demand)
    return values


def read_thermal_demand(path):
    """Read hourly thermal demand and compute total heat demand."""
    values = []
    with path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            space = parse_float(row[THERMAL_SPACE_COLUMN])
            water = parse_float(row[THERMAL_WATER_COLUMN])
            values.append(space + water)
    return values


def write_hourly_results(path, rows):
    """Write hourly result rows to a CSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    hourly_results = []
    total_electricity_demand = 0.0
    total_thermal_demand = 0.0

    for season_name, electricity_path, thermal_path in SEASON_FILES:
        electricity_demand = read_electricity_demand(electricity_path)
        thermal_demand = read_thermal_demand(thermal_path)

        for hour_index, (electricity_kwh, thermal_kwh) in enumerate(
            zip(electricity_demand, thermal_demand), start=1
        ):
            utility_grid_supply_kwh = electricity_kwh
            gas_boiler_heat_kwh = thermal_kwh

            cost_utility_grid_eur = utility_grid_supply_kwh * ELECTRICITY_PRICE_EUR_PER_KWH
            cost_gas_boiler_eur = gas_boiler_heat_kwh * GAS_BOILER_LCOH_EUR_PER_KWH

            emissions_utility_grid_kg = utility_grid_supply_kwh * UTILITY_GRID_EMISSION_FACTOR_KG_PER_KWH
            emissions_gas_boiler_kg = gas_boiler_heat_kwh * GAS_BOILER_EMISSION_FACTOR_KG_PER_KWH

            total_cost_hour_eur = cost_utility_grid_eur + cost_gas_boiler_eur
            total_emissions_hour_kg = emissions_utility_grid_kg + emissions_gas_boiler_kg

            total_electricity_demand += electricity_kwh
            total_thermal_demand += thermal_kwh

            hourly_results.append(
                {
                    "season": season_name,
                    "hour": hour_index,
                    "electricity_demand_kwh": round(electricity_kwh, 4),
                    "thermal_demand_kwh": round(thermal_kwh, 4),
                    "utility_grid_supply_kwh": round(utility_grid_supply_kwh, 4),
                    "gas_boiler_heat_kwh": round(gas_boiler_heat_kwh, 4),
                    "cost_utility_grid_eur": round(cost_utility_grid_eur, 4),
                    "cost_gas_boiler_eur": round(cost_gas_boiler_eur, 4),
                    "emissions_utility_grid_kg": round(emissions_utility_grid_kg, 4),
                    "emissions_gas_boiler_kg": round(emissions_gas_boiler_kg, 4),
                    "total_cost_hour_eur": round(total_cost_hour_eur, 4),
                    "total_emissions_hour_kg": round(total_emissions_hour_kg, 4),
                }
            )

    # Annual calculations are based on summed representative demands multiplied by 91.25
    annual_cost_ug = total_electricity_demand * ELECTRICITY_PRICE_EUR_PER_KWH * ANNUALIZATION_FACTOR
    annual_cost_gb = total_thermal_demand * GAS_BOILER_LCOH_EUR_PER_KWH * ANNUALIZATION_FACTOR
    annual_emissions_ug = total_electricity_demand * UTILITY_GRID_EMISSION_FACTOR_KG_PER_KWH * ANNUALIZATION_FACTOR
    annual_emissions_gb = total_thermal_demand * GAS_BOILER_EMISSION_FACTOR_KG_PER_KWH * ANNUALIZATION_FACTOR
    annual_cost_total = annual_cost_ug + annual_cost_gb
    annual_emissions_total = annual_emissions_ug + annual_emissions_gb

    write_hourly_results(OUTPUT_FILE, hourly_results)

    print("Scenario 1 summary:")
    print(f"  seasons processed: {len(SEASON_FILES)}")
    print(f"  rows written: {len(hourly_results)}")
    print(f"  annual cost utility grid (EUR): {annual_cost_ug:.2f}")
    print(f"  annual cost gas boiler (EUR): {annual_cost_gb:.2f}")
    print(f"  annual total cost (EUR): {annual_cost_total:.2f}")
    print(f"  annual emissions utility grid (kg CO2e): {annual_emissions_ug:.2f}")
    print(f"  annual emissions gas boiler (kg CO2e): {annual_emissions_gb:.2f}")
    print(f"  annual total emissions (kg CO2e): {annual_emissions_total:.2f}")
    print(f"  hourly results written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
