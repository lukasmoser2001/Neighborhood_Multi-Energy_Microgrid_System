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


# ... all existing helper functions from main.py (apply_component_parameters, build_result_fields, etc.)
# are kept unchanged below this point.
# Only the data-loading utilities have been moved to data_loading.py and imported above.

# (Paste the full content of your current main.py below this comment, starting from
# apply_component_parameters and leaving out BASE_DIR, file paths, and read_* functions,
# which now live in data_loading.py.)
