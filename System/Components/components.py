from pathlib import Path
import csv
import json

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


class PVSystem:
    def __init__(self, config: dict | None = None):
        cfg = config if config is not None else COMPONENT_PARAMETERS.get("pv_system", {})
        self.enabled = cfg.get("enabled", False)
        if not self.enabled:
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
        return _get_heat_pump_cop(self.cop_series, season_index, hour_index)

    def get_electricity_demand_kwh(self, thermal_kwh: float, season_index: int, hour_index: int) -> float:
        cop = self.get_cop(season_index, hour_index)
        return thermal_kwh / cop if cop > 0 else 0.0

    def get_cost_eur(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.lcoh_eur_per_kwh if self.enabled else 0.0

    def get_emissions_kg(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.emission_factor_kg_per_kwh if self.enabled else 0.0


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
        return _get_heat_pump_cop(self.cop_series, season_index, hour_index)

    def get_electricity_demand_kwh(self, thermal_kwh: float, season_index: int, hour_index: int) -> float:
        cop = self.get_cop(season_index, hour_index)
        return thermal_kwh / cop if cop > 0 else 0.0

    def get_cost_eur(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.lcoh_eur_per_kwh if self.enabled else 0.0

    def get_emissions_kg(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.emission_factor_kg_per_kwh if self.enabled else 0.0


class BatteryStorage:
    def __init__(self, config: dict | None = None):
        cfg = config if config is not None else COMPONENT_PARAMETERS.get("BESS", {})
        self.enabled = cfg.get("enabled", False)
        if not self.enabled:
            self.E_cap = 0.0
            self.soc_init_frac = 0.5
            self.soc = 0.0
            self.eta_char = 1.0
            self.eta_disc = 1.0
            self.sigma = 0.0
            self.P_max = 0.0
            self.LCOS = 0.0
            self.CO2eq_BES_annual = 0.0
            return
        try:
            self.E_cap = cfg["E_cap_kwh"]
            self.soc_init_frac = cfg.get("soc_init_frac", 0.5)
            self.eta_char = cfg["eta_char"]
            self.eta_disc = cfg["eta_disc"]
            self.sigma = cfg.get("sigma_per_hour", 0.0)
            self.P_max = cfg["P_max_kw"]
            self.LCOS = cfg["lcos_eur_per_kwh"]
            self.CO2eq_BES_annual = cfg.get("CO2eq_BES_annual_kg", 0.0)
        except KeyError as e:
            raise ValueError(f"Missing required parameter {e.args[0]!r} for BatteryStorage in component_parameters.json")
        self.soc = self.E_cap * self.soc_init_frac

    def reset_soc(self) -> None:
        # reset SOC to initial fraction
        self.soc = self.E_cap * self.soc_init_frac

    def get_soc_target_kwh(self) -> float:
        # target SOC in kWh for end-of-day restoration
        return self.E_cap * self.soc_init_frac

    def force_soc_to_target(self) -> float:
        # force SOC to target; returns signed delta (+ = draw from grid, - = export)
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

    def get_charge_energy_input(self, charge_kwh: float) -> float:
        return charge_kwh / self.eta_char if self.eta_char else 0.0

    def get_discharge_energy_output(self, discharge_kwh: float) -> float:
        return discharge_kwh * self.eta_disc

    def get_cost_eur(self, charge_kwh: float) -> float:
        # LCOS [€/kWh] x energy charged into battery
        return charge_kwh * self.LCOS if self.enabled else 0.0


class ThermalEnergyStorage:
    def __init__(self, config: dict | None = None):
        cfg = config if config is not None else COMPONENT_PARAMETERS.get("TESS", {})
        self.enabled = cfg.get("enabled", False)
        if not self.enabled:
            self.E_cap = 0.0
            self.soc_init_frac = 0.5
            self.soc = 0.0
            self.eta_char = 1.0
            self.eta_disc = 1.0
            self.sigma = 0.0
            self.lcoh = 0.0
            self.emission_factor_kg_per_kwh = 0.0
            return
        try:
            self.E_cap = cfg["E_cap_kwh"]
            self.soc_init_frac = cfg.get("soc_init_frac", 0.5)
            self.eta_char = cfg.get("eta_char", 1.0)
            self.eta_disc = cfg.get("eta_disc", 1.0)
            self.sigma = cfg.get("sigma_per_hour", 0.0)
            self.lcoh = cfg["lcoh_eur_per_kwh"]
            self.emission_factor_kg_per_kwh = cfg.get("emission_factor_kg_per_kwh", 0.0)
        except KeyError as e:
            raise ValueError(f"Missing required parameter {e.args[0]!r} for ThermalEnergyStorage in component_parameters.json")
        self.soc = self.E_cap * self.soc_init_frac

    def reset_soc(self) -> None:
        # reset SOC to initial fraction
        self.soc = self.E_cap * self.soc_init_frac

    def get_soc_target_kwh(self) -> float:
        # target SOC in kWh for end-of-day restoration
        return self.E_cap * self.soc_init_frac

    def force_soc_to_target(self) -> float:
        # force SOC to target; returns signed delta (+ = draw from grid, - = export)
        target = self.get_soc_target_kwh()
        delta = target - self.soc
        self.soc = target
        return delta

    def available_charge_capacity_kwh(self) -> float:
        return max(0.0, self.E_cap - self.soc)

    def get_discharge_for_demand(self, thermal_demand_kwh: float) -> float:
        available = self.soc * self.eta_disc
        return min(thermal_demand_kwh, available)

    def get_heat_from_discharge(self, discharge_kwh: float) -> float:
        return discharge_kwh

    def get_charge_from_heat_source(self, heat_available_kwh: float) -> float:
        capacity = self.available_charge_capacity_kwh()
        return min(heat_available_kwh * self.eta_char, capacity)

    def update_state(self, q_tess_in: float, q_tess_out: float) -> None:
        self.soc += q_tess_in * self.eta_char - q_tess_out / self.eta_disc
        self.soc = max(0.0, min(self.soc, self.E_cap))
        self.soc *= (1.0 - self.sigma)

    def get_cost_eur(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.lcoh if self.enabled else 0.0

    def get_emissions_kg(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.emission_factor_kg_per_kwh if self.enabled else 0.0
