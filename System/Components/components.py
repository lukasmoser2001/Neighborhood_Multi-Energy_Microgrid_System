from pathlib import Path
import csv
import json

# Load component parameters from Data/Components/component_parameters.json so
# values are managed centrally and changes there propagate automatically.
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_COMPONENT_PARAMETERS_FILE = _BASE_DIR / "Data" / "Components" / "component_parameters.json"
try:
    with _COMPONENT_PARAMETERS_FILE.open("r", encoding="utf-8") as _f:
        COMPONENT_PARAMETERS = json.load(_f)
except Exception:
    COMPONENT_PARAMETERS = {}

_HEAT_COP_FILES = [
    _BASE_DIR / "Data" / "Load" / "Heat" / "extracted_when2heat_FR_15_01_2015.csv",
    _BASE_DIR / "Data" / "Load" / "Heat" / "extracted_when2heat_FR_15_04_2015.csv",
    _BASE_DIR / "Data" / "Load" / "Heat" / "extracted_when2heat_FR_15_07_2015.csv",
    _BASE_DIR / "Data" / "Load" / "Heat" / "extracted_when2heat_FR_15_10_2015.csv",
]

def _parse_float(value: str) -> float:
    if value is None or value == "":
        return 0.0
    return float(value.replace(",", "."))

def _load_heat_cop_data(column_name: str) -> list[list[float]]:
    data = []
    for path in _HEAT_COP_FILES:
        values = []
        with path.open(newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                values.append(_parse_float(row.get(column_name, "0")))
        data.append(values)
    return data

_HEAT_COP_ASHP_WATER_COLUMN = "FR_COP_ASHP_water"
_HEAT_COP_GSHP_FLOOR_COLUMN = "FR_COP_GSHP_floor"
_HEAT_COP_SERIES = {
    "air": _load_heat_cop_data(_HEAT_COP_ASHP_WATER_COLUMN),
    "ground": _load_heat_cop_data(_HEAT_COP_GSHP_FLOOR_COLUMN),
}


def _get_heat_pump_cop(series: list[list[float]], season_index: int, hour_index: int) -> float:
    if season_index < 0 or season_index >= len(series):
        return 0.0
    season_data = series[season_index]
    if hour_index < 0 or hour_index >= len(season_data):
        return 0.0
    return max(0.0, season_data[hour_index])


# Utility grid component
# Parameters (in component_parameters.json -> "utility_grid"):
# - electricity_price_eur_per_kwh: €/kWh, electricity price from utility grid
# - emission_factor_kg_per_kwh: kg CO2/kWh, emissions from grid electricity
class UtilityGrid:
    def __init__(self, config: dict | None = None):
        cfg = config if config is not None else COMPONENT_PARAMETERS.get("utility_grid", {})
        self.enabled = cfg.get("enabled", False)
        if not self.enabled:
            self.electricity_price_eur_per_kwh = 0.0
            self.sell_price_eur_per_kwh = 0.0
            self.emission_factor_kg_per_kwh = 0.0
            return
        try:
            self.electricity_price_eur_per_kwh = cfg["electricity_price_eur_per_kwh"]
            self.sell_price_eur_per_kwh = cfg["sell_price_eur_per_kwh"]
            self.emission_factor_kg_per_kwh = cfg["emission_factor_kg_per_kwh"]
        except KeyError as e:
            raise ValueError(f"Missing required parameter {e.args[0]!r} for UtilityGrid in component_parameters.json")

    def get_cost_eur(self, electricity_kwh: float) -> float:
        return electricity_kwh * self.electricity_price_eur_per_kwh

    def get_revenue_eur(self, export_kwh: float) -> float:
        return export_kwh * self.sell_price_eur_per_kwh

    def get_emissions_kg(self, electricity_kwh: float) -> float:
        return electricity_kwh * self.emission_factor_kg_per_kwh


# PV system component
# Parameters (in component_parameters.json -> "pv_system"):
# - i_stc_w_m2: W/m², STC irradiance
# - t_stc_c: °C, STC cell temperature
# - i_ref_w_m2: W/m², reference irradiance for temperature model
# - t_ref_c: °C, reference ambient temperature
# - t_nom_c: °C, Nominal Module Operating Temperature (NOCT)
# - beta_per_c: per °C, temperature coefficient
# - panel_area_m2: m², area per panel
# - panels_per_household: number of panels per household
# - power_density_w_m2: W/m², power density of panel
# - annualized_capital_cost_per_panel_eur: €/year, annualized capital cost per panel
# - o_and_m_cost_per_kwh_eur: €/kWh, O&M cost per kWh
class PVSystem:
    def __init__(self, config: dict | None = None):
        cfg = config if config is not None else COMPONENT_PARAMETERS.get("pv_system", {})
        # Require explicit enabling in the JSON file
        self.enabled = cfg.get("enabled", False)
        if not self.enabled:
            # Neutral fallbacks
            self.i_stc = 1000.0
            self.t_stc = 25.0
            self.i_ref = 800.0
            self.t_ref = 20.0
            self.t_nom = 44.0
            self.beta = 0.0
            self.panel_area_m2 = 0.0
            self.panels_per_household = 0
            self.power_density_w_m2 = 0.0
            self.capex_per_panel_eur = 0.0
            self.om_cost_per_kwh = 0.0
            self.p_pv_peak_kw = 0.0
            self.capex_total_eur = 0.0
            return
        try:
            self.i_stc = cfg["i_stc_w_m2"]
            self.t_stc = cfg["t_stc_c"]
            self.i_ref = cfg["i_ref_w_m2"]
            self.t_ref = cfg["t_ref_c"]
            self.t_nom = cfg["t_nom_c"]
            self.beta = cfg["beta_per_c"]
            self.panel_area_m2 = cfg["panel_area_m2"]
            self.panels_per_household = cfg["panels_per_household"]
            self.power_density_w_m2 = cfg["power_density_w_m2"]
            self.capex_per_panel_eur = cfg["annualized_capital_cost_per_panel_eur"]
            self.om_cost_per_kwh = cfg["o_and_m_cost_per_kwh_eur"]
        except KeyError as e:
            raise ValueError(f"Missing required parameter {e.args[0]!r} for PVSystem in component_parameters.json")
        self.p_pv_peak_kw = self.power_density_w_m2 * self.panel_area_m2 * self.panels_per_household / 1000.0
        self.capex_total_eur = self.capex_per_panel_eur * self.panels_per_household

    def calc_pv_temperature(self, t_amb: float, irradiance: float) -> float:
        return t_amb + (self.t_nom - self.t_ref) * (irradiance / self.i_ref)

    def calc_pv_output_kwh(self, irradiance: float, t_amb: float) -> float:
        t_pv = self.calc_pv_temperature(t_amb, irradiance)
        p_pv_w = self.p_pv_peak_kw * 1000 * (irradiance / self.i_stc) * (1.0 - self.beta * (t_pv - self.t_stc))
        return max(0.0, p_pv_w) / 1000.0

    def get_capex_hour_eur(self, annualization_factor: float) -> float:
        return self.capex_total_eur / (annualization_factor * 24.0)

    def get_om_cost_eur(self, pv_output_kwh: float) -> float:
        return pv_output_kwh * self.om_cost_per_kwh


# Gas boiler component
# Parameters (in component_parameters.json -> "gas_boiler"):
# - lcoh_eur_per_kwh: €/kWh, levelized cost of heat
# - emission_factor_kg_per_kwh: kg CO2/kWh, emissions from gas combustion
class GasBoiler:
    def __init__(self, config: dict | None = None):
        cfg = config if config is not None else COMPONENT_PARAMETERS.get("gas_boiler", {})
        self.enabled = cfg.get("enabled", False)
        if not self.enabled:
            self.lcoh_eur_per_kwh = 0.0
            self.emission_factor_kg_per_kwh = 0.0
            return
        try:
            self.lcoh_eur_per_kwh = cfg["lcoh_eur_per_kwh"]
            self.emission_factor_kg_per_kwh = cfg["emission_factor_kg_per_kwh"]
        except KeyError as e:
            raise ValueError(f"Missing required parameter {e.args[0]!r} for GasBoiler in component_parameters.json")

    def get_cost_eur(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.lcoh_eur_per_kwh

    def get_emissions_kg(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.emission_factor_kg_per_kwh


# Electric boiler component
# Parameters (in component_parameters.json -> "electric_boiler"):
# - efficiency: conversion efficiency from electricity to heat (0-1)
# - lcoh_eur_per_kwh: €/kWh, levelized cost of heat (additionally to the electricity cost)
# - emission_factor_kg_per_kwh: kg CO2/kWh, direct emissions (indirect emissions from electric boiler production might get added later))
class ElectricBoiler:
    def __init__(self, config: dict | None = None):
        cfg = config if config is not None else COMPONENT_PARAMETERS.get("electric_boiler", {})
        self.enabled = cfg.get("enabled", False)
        if not self.enabled:
            self.efficiency = 0.0
            self.lcoh_eur_per_kwh = 0.0
            self.emission_factor_kg_per_kwh = 0.0
            return
        try:
            self.efficiency = cfg["efficiency"]
            self.lcoh_eur_per_kwh = cfg["lcoh_eur_per_kwh"]
            self.emission_factor_kg_per_kwh = cfg["emission_factor_kg_per_kwh"]
        except KeyError as e:
            raise ValueError(f"Missing required parameter {e.args[0]!r} for ElectricBoiler in component_parameters.json")

    def get_electricity_demand_kwh(self, thermal_kwh: float) -> float:
        return thermal_kwh / self.efficiency if self.efficiency else float("inf")

    def get_cost_eur(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.lcoh_eur_per_kwh

    def get_emissions_kg(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.emission_factor_kg_per_kwh


# Heat pump air-source component
# Parameters (in component_parameters.json -> "heat_pump_air"):
# - lcoh_eur_per_kwh: €/kWh, levelized cost of heat
# - emission_factor_kg_per_kwh: kg CO2/kWh, direct emissions (no direct emissions; indirect maybe added later; for now only due to added electricity consumption taken into account)
class HeatPumpAir:
    def __init__(self, config: dict | None = None):
        cfg = config if config is not None else COMPONENT_PARAMETERS.get("heat_pump_air", {})
        self.enabled = cfg.get("enabled", False)
        if not self.enabled:
            self.lcoh_eur_per_kwh = 0.0
            self.emission_factor_kg_per_kwh = 0.0
            self.cop_series = []
            return
        try:
            self.lcoh_eur_per_kwh = cfg["lcoh_eur_per_kwh"]
            self.emission_factor_kg_per_kwh = cfg["emission_factor_kg_per_kwh"]
        except KeyError as e:
            raise ValueError(f"Missing required parameter {e.args[0]!r} for HeatPumpAir in component_parameters.json")
        self.cop_series = _HEAT_COP_SERIES["air"]

    def get_cop(self, season_index: int, hour_index: int) -> float:
        if not self.enabled:
            return 0.0
        return _get_heat_pump_cop(self.cop_series, season_index, hour_index)

    def get_electricity_demand_kwh(self, thermal_kwh: float, season_index: int, hour_index: int) -> float:
        if not self.enabled or thermal_kwh <= 0.0:
            return 0.0
        cop = self.get_cop(season_index, hour_index)
        return thermal_kwh / cop if cop > 0.0 else 0.0

    def get_cost_eur(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.lcoh_eur_per_kwh if self.enabled else 0.0

    def get_emissions_kg(self, thermal_kwh: float) -> float:
        return 0.0


# Heat pump ground-source component
# Parameters (in component_parameters.json -> "heat_pump_ground"):
# - lcoh_eur_per_kwh: €/kWh, levelized cost of heat
# - emission_factor_kg_per_kwh: kg CO2/kWh, direct emissions
class HeatPumpGround:
    def __init__(self, config: dict | None = None):
        cfg = config if config is not None else COMPONENT_PARAMETERS.get("heat_pump_ground", {})
        self.enabled = cfg.get("enabled", False)
        if not self.enabled:
            self.lcoh_eur_per_kwh = 0.0
            self.emission_factor_kg_per_kwh = 0.0
            self.cop_series = []
            return
        try:
            self.lcoh_eur_per_kwh = cfg["lcoh_eur_per_kwh"]
            self.emission_factor_kg_per_kwh = cfg["emission_factor_kg_per_kwh"]
        except KeyError as e:
            raise ValueError(f"Missing required parameter {e.args[0]!r} for HeatPumpGround in component_parameters.json")
        self.cop_series = _HEAT_COP_SERIES["ground"]

    def get_cop(self, season_index: int, hour_index: int) -> float:
        if not self.enabled:
            return 0.0
        return _get_heat_pump_cop(self.cop_series, season_index, hour_index)

    def get_electricity_demand_kwh(self, thermal_kwh: float, season_index: int, hour_index: int) -> float:
        if not self.enabled or thermal_kwh <= 0.0:
            return 0.0
        cop = self.get_cop(season_index, hour_index)
        return thermal_kwh / cop if cop > 0.0 else 0.0

    def get_cost_eur(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.lcoh_eur_per_kwh if self.enabled else 0.0

    def get_emissions_kg(self, thermal_kwh: float) -> float:
        return 0.0


# Battery energy storage system component
# Parameters (in component_parameters.json -> "BESS"):
# - sigma_BES: self-discharge rate per timestep
# - eta_BES_char: charging efficiency
# - eta_BES_disc: discharging efficiency
# - SOC_BES_init: SOC reset fraction at midnight each day
# - SOC_BES_min: minimum SOC fraction
# - SOC_BES_max: maximum SOC fraction
# - E_BES_cap: usable energy capacity in kWh
# - P_BES_max: maximum charge/discharge power in kW
# - LCOS: levelized cost of storage capacity in €/kWh
# - LEOS: lifecycle emissions intensity in kgCO2eq/kWh
# - CO2eq_BES: total lifecycle emissions in kgCO2eq
# - lifetime_BES: lifetime in years
# - CO2eq_BES_annual: annualized lifecycle emissions in kgCO2eq/year
class BatteryStorage:
    def __init__(self, config: dict | None = None):
        cfg = config if config is not None else COMPONENT_PARAMETERS.get("BESS", {})
        self.enabled = cfg.get("enabled", False)
        if not self.enabled:
            self.sigma = 0.0
            self.eta_char = 1.0
            self.eta_disc = 1.0
            self.soc_init = 0.0
            self.soc_min = 0.0
            self.soc_max = 1.0
            self.E_cap = 0.0
            self.P_max = 0.0
            self.LCOS = 0.0
            self.LEOS = 0.0
            self.CO2eq_BES = 0.0
            self.lifetime = 0
            self.CO2eq_BES_annual = 0.0
            self.soc = 0.0
            return
        try:
            self.sigma = cfg["sigma_BES"]
            self.eta_char = cfg["eta_BES_char"]
            self.eta_disc = cfg["eta_BES_disc"]
            self.soc_init = cfg["SOC_BES_init"]
            self.soc_min = cfg["SOC_BES_min"]
            self.soc_max = cfg["SOC_BES_max"]
            self.E_cap = cfg["E_BES_cap"]
            self.P_max = cfg["P_BES_max"]
            self.LCOS = cfg["LCOS"]
            self.LEOS = cfg["LEOS"]
            self.CO2eq_BES = cfg["CO2eq_BES"]
            self.lifetime = cfg["lifetime_BES"]
            self.CO2eq_BES_annual = cfg["CO2eq_BES_annual"]
            self.soc = self.soc_init * self.E_cap
        except KeyError as e:
            raise ValueError(f"Missing required parameter {e.args[0]!r} for BatteryStorage in component_parameters.json")

    def reset_soc(self) -> None:
        self.soc = self.soc_init * self.E_cap

    def get_soc_target_kwh(self) -> float:
        # Target SOC in kWh to restore at end of day
        return self.soc_init * self.E_cap

    def force_soc_to_target(self) -> float:
        # Returns signed delta: positive = deficit (buy from grid), negative = surplus (sell to grid)
        target = self.get_soc_target_kwh()
        delta = target - self.soc
        self.soc = target
        return delta

    def get_charge_energy_input(self, power_kw: float) -> float:
        return self.eta_char * max(0.0, min(power_kw, self.P_max))

    def get_discharge_energy_output(self, power_kw: float) -> float:
        return max(0.0, min(power_kw, self.P_max)) / self.eta_disc

    def available_charge_capacity_kwh(self) -> float:
        return max(0.0, self.soc_max * self.E_cap - self.soc)

    def available_discharge_capacity_kwh(self) -> float:
        return max(0.0, self.soc - self.soc_min * self.E_cap)

    def apply_self_discharge(self) -> None:
        self.soc = self.soc * (1.0 - self.sigma)

    def clamp_soc(self) -> None:
        self.soc = min(max(self.soc, self.soc_min * self.E_cap), self.soc_max * self.E_cap)


# Thermal energy storage system component
# Parameters (in component_parameters.json -> "TESS"):
# - E_TESS_cap: kWh, usable thermal storage capacity
# - sigma_TESS: self-discharge rate per timestep
# - eta_PHE: plate heat exchanger efficiency
# - SOC_TESS_12am: SOC reset fraction at midnight each day
# - LCOH_TESS: €/kWh, levelized cost of heat
# - LEOH_TESS: kgCO2eq/kWh, lifecycle emissions intensity
class ThermalEnergyStorage:
    def __init__(self, config: dict | None = None):
        cfg = config if config is not None else COMPONENT_PARAMETERS.get("TESS", {})
        self.enabled = cfg.get("enabled", False)
        if not self.enabled:
            self.sigma = 0.0
            self.eta_phe = 1.0
            self.soc_init = 0.0
            self.E_cap = 0.0
            self.lcoh = 0.0
            self.leoh = 0.0
            self.soc = 0.0
            return
        try:
            self.sigma = cfg["sigma_TESS"]
            self.eta_phe = cfg["eta_PHE"]
            self.soc_init = cfg["SOC_TESS_12am"]
            self.E_cap = cfg["E_TESS_cap"]
            self.lcoh = cfg["LCOH_TESS"]
            self.leoh = cfg["LEOH_TESS"]
        except KeyError as e:
            raise ValueError(f"Missing required parameter {e.args[0]!r} for ThermalEnergyStorage in component_parameters.json")
        self.soc = self.soc_init * self.E_cap

    def reset_soc(self) -> None:
        self.soc = self.soc_init * self.E_cap

    def get_soc_target_kwh(self) -> float:
        # Target SOC in kWh to restore at end of day
        return self.soc_init * self.E_cap
    
    def force_soc_to_target(self) -> float:
        # Returns signed delta: positive = deficit (generate heat), negative = surplus (discard)
        target = self.get_soc_target_kwh()
        delta = target - self.soc
        self.soc = target
        return delta

    def available_charge_capacity_kwh(self) -> float:
        return max(0.0, self.E_cap - self.soc)

    def available_discharge_capacity_kwh(self) -> float:
        return max(0.0, self.soc)

    def apply_self_discharge(self) -> None:
        self.soc = self.soc * (1.0 - self.sigma)

    def clamp_soc(self) -> None:
        self.soc = min(max(self.soc, 0.0), self.E_cap)

    def get_discharge_for_demand(self, thermal_demand_kwh: float) -> float:
        if not self.enabled or thermal_demand_kwh <= 0.0:
            return 0.0
        return min(thermal_demand_kwh / self.eta_phe, self.available_discharge_capacity_kwh())

    def get_heat_from_discharge(self, q_tess_out: float) -> float:
        return max(0.0, q_tess_out * self.eta_phe)

    def get_charge_from_heat_source(self, thermal_input_kwh: float) -> float:
        if not self.enabled or thermal_input_kwh <= 0.0:
            return 0.0
        return min(thermal_input_kwh, self.available_charge_capacity_kwh())

    def dispatch_for_demand(self, thermal_demand_kwh: float) -> tuple[float, float, float]:
        q_tess_out = self.get_discharge_for_demand(thermal_demand_kwh)
        heat_supplied = self.get_heat_from_discharge(q_tess_out)
        remaining_demand = max(0.0, thermal_demand_kwh - heat_supplied)
        self.update_state(q_tess_in=0.0, q_tess_out=q_tess_out)
        return q_tess_out, heat_supplied, remaining_demand

    def update_state(self, q_tess_in: float, q_tess_out: float) -> None:
        if not self.enabled:
            return
        self.soc = self.soc * (1.0 - self.sigma) + q_tess_in - q_tess_out
        self.clamp_soc()

    def get_cost_eur(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.lcoh if self.enabled else 0.0

    def get_emissions_kg(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.leoh if self.enabled else 0.0

