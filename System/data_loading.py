from datetime import datetime, timezone
from pathlib import Path
import csv
import json
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent

COMPONENT_PARAMETERS_FILE = BASE_DIR / "Data" / "Components" / "component_parameters.json"
ELECTRICITY_DATA_FILE = BASE_DIR / "Data" / "Load" / "Electricity" / "gas_house-summary.csv"
THERMAL_DATA_FILE = BASE_DIR / "Data" / "Load" / "Heat" / "extracted_when2heat_FR_2015.csv"
SOLAR_DATA_FILE = BASE_DIR / "Data" / "SolarIrradiation" / "It_Tamb_Compiegne_2023.csv"

ELECTRICITY_COLUMN_NAME = "Mean"
THERMAL_SPACE_COLUMN = "FR_heat_demand_space_SFH"
THERMAL_WATER_COLUMN = "FR_heat_demand_water"
HEAT_COP_ASHP_WATER_COLUMN = "FR_COP_ASHP_water"


def parse_float(value: str) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return 0.0


def parse_timestamp(value: str) -> datetime:
    text = str(value).strip()
    if not text:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text.replace(" ", "T"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def read_electricity_demand(path: Path) -> list[tuple[datetime, float]]:
    values: list[tuple[datetime, float]] = []
    with path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        timestamp_field = reader.fieldnames[0] if reader.fieldnames else ""
        start_date = datetime(2022, 10, 25, tzinfo=timezone.utc)
        end_date = datetime(2023, 10, 25, tzinfo=timezone.utc)

        current_hour: datetime | None = None
        current_hour_energy_wh = 0.0
        for row in reader:
            timestamp = parse_timestamp(row[timestamp_field])
            if not (start_date <= timestamp < end_date):
                continue

            hour_start = timestamp.replace(minute=0, second=0, microsecond=0)
            if current_hour is None:
                current_hour = hour_start
            if hour_start != current_hour:
                values.append((current_hour, current_hour_energy_wh / 1000.0))
                current_hour = hour_start
                current_hour_energy_wh = 0.0

            current_hour_energy_wh += parse_float(row[ELECTRICITY_COLUMN_NAME])

        if current_hour is not None:
            values.append((current_hour, current_hour_energy_wh / 1000.0))

    return values


def read_thermal_demand(path: Path) -> list[tuple[datetime, float]]:
    values: list[tuple[datetime, float]] = []
    with path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            timestamp = parse_timestamp(row["utc_timestamp"])
            space = parse_float(row[THERMAL_SPACE_COLUMN])
            water = parse_float(row[THERMAL_WATER_COLUMN])
            values.append((timestamp, (space + water) / 1000.0))
    return values


def read_solar_data(path: Path) -> list[tuple[datetime, float, float]]:
    values: list[tuple[datetime, float, float]] = []
    with path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            timestamp = parse_timestamp(row["timestamp"])
            irradiance = parse_float(row["I(t)_Wm2"])
            t_amb = parse_float(row["Tamb_C"])
            values.append((timestamp, irradiance, t_amb))
    return values


def load_heat_pump_cop_series(path: Path, column_name: str = HEAT_COP_ASHP_WATER_COLUMN) -> list[list[float]]:
    values: list[list[float]] = []
    with path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        day_values: list[float] = []
        for row in reader:
            day_values.append(parse_float(row.get(column_name, "0")))
            if len(day_values) == 24:
                values.append(day_values)
                day_values = []
        if day_values:
            values.append(day_values)
    return values


def load_component_parameters(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Component parameters file not found: {path}")
    with path.open("r", encoding="utf-8") as jsonfile:
        return json.load(jsonfile)


def upscale_demand_series(
    base_series: list[tuple[datetime, float]],
    n_households: int,
    sigma_log: float,
    coincidence_alpha: float,
    seed: int,
) -> list[tuple[datetime, float]]:
    rng = np.random.default_rng(seed=seed)
    mu_log = -0.5 * sigma_log ** 2
    scaling_factors = rng.lognormal(mean=mu_log, sigma=sigma_log, size=n_households)
    cf = float(np.clip(
        (1.0 / np.sqrt(n_households)) * (1.0 - coincidence_alpha) + coincidence_alpha,
        0.0, 1.0
    ))
    return [(ts, float(np.sum(base_val * scaling_factors) * cf)) for ts, base_val in base_series]
