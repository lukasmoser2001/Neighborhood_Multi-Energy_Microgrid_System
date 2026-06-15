from pathlib import Path
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


# Utility grid component
# Parameters (in component_parameters.json -> "utility_grid"):
# - electricity_price_eur_per_kwh: €/kWh, electricity price from utility grid
# - emission_factor_kg_per_kwh: kg CO2/kWh, emissions from grid electricity
class UtilityGrid:
    def __init__(self, config: dict | None = None):
        # If no explicit config passed, read from JSON file
        cfg = config if config is not None else COMPONENT_PARAMETERS.get("utility_grid", {})
        self.enabled = cfg.get("enabled", True)
        self.electricity_price_eur_per_kwh = cfg.get("electricity_price_eur_per_kwh", 0.0)
        self.sell_price_eur_per_kwh = cfg.get("sell_price_eur_per_kwh", 0.0)
        self.emission_factor_kg_per_kwh = cfg.get("emission_factor_kg_per_kwh", 0.0)

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
        self.enabled = cfg.get("enabled", True)
        self.i_stc = cfg.get("i_stc_w_m2", 1000.0)
        self.t_stc = cfg.get("t_stc_c", 25.0)
        self.i_ref = cfg.get("i_ref_w_m2", 800.0)
        self.t_ref = cfg.get("t_ref_c", 20.0)
        self.t_nom = cfg.get("t_nom_c", 44.0)
        self.beta = cfg.get("beta_per_c", 0.0024)
        self.panel_area_m2 = cfg.get("panel_area_m2", 2.08)
        self.panels_per_household = cfg.get("panels_per_household", 6)
        self.power_density_w_m2 = cfg.get("power_density_w_m2", 224)
        self.capex_per_panel_eur = cfg.get("annualized_capital_cost_per_panel_eur", 0.0)
        self.om_cost_per_kwh = cfg.get("o_and_m_cost_per_kwh_eur", 0.0)
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
        self.enabled = cfg.get("enabled", True)
        self.lcoh_eur_per_kwh = cfg.get("lcoh_eur_per_kwh", 0.0)
        self.emission_factor_kg_per_kwh = cfg.get("emission_factor_kg_per_kwh", 0.0)

    def get_cost_eur(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.lcoh_eur_per_kwh

    def get_emissions_kg(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.emission_factor_kg_per_kwh


# Electric boiler component
# Parameters (in component_parameters.json -> "electric_boiler"):
# - efficiency: conversion efficiency from electricity to heat (0-1)
# - lcoh_eur_per_kwh: €/kWh, levelized cost of heat (for bookkeeping)
# - emission_factor_kg_per_kwh: kg CO2/kWh, direct emissions (usually 0)
class ElectricBoiler:
    def __init__(self, config: dict | None = None):
        cfg = config if config is not None else COMPONENT_PARAMETERS.get("electric_boiler", {})
        self.enabled = cfg.get("enabled", False)
        self.efficiency = cfg.get("efficiency", 1.0)
        self.lcoh_eur_per_kwh = cfg.get("lcoh_eur_per_kwh", 0.0)
        self.emission_factor_kg_per_kwh = cfg.get("emission_factor_kg_per_kwh", 0.0)

    def get_electricity_demand_kwh(self, thermal_kwh: float) -> float:
        return thermal_kwh / self.efficiency if self.efficiency else float("inf")

    def get_cost_eur(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.lcoh_eur_per_kwh

    def get_emissions_kg(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.emission_factor_kg_per_kwh


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
        self.enabled = cfg.get("enabled", True)
        self.sigma = cfg.get("sigma_BES", 0.0)
        self.eta_char = cfg.get("eta_BES_char", 1.0)
        self.eta_disc = cfg.get("eta_BES_disc", 1.0)
        self.soc_init = cfg.get("SOC_BES_init", 0.0)
        self.soc_min = cfg.get("SOC_BES_min", 0.0)
        self.soc_max = cfg.get("SOC_BES_max", 1.0)
        self.E_cap = cfg.get("E_BES_cap", 0.0)
        self.P_max = cfg.get("P_BES_max", 0.0)
        self.LCOS = cfg.get("LCOS", 0.0)
        self.LEOS = cfg.get("LEOS", 0.0)
        self.CO2eq_BES = cfg.get("CO2eq_BES", 0.0)
        self.lifetime = cfg.get("lifetime_BES", 0)
        self.CO2eq_BES_annual = cfg.get("CO2eq_BES_annual", 0.0)
        self.soc = self.soc_init * self.E_cap

    def reset_soc(self) -> None:
        self.soc = self.soc_init * self.E_cap

    def get_charge_energy_input(self, power_kw: float, delta_t: float = 1.0) -> float:
        return self.eta_char * max(0.0, min(power_kw, self.P_max)) * delta_t

    def get_discharge_energy_output(self, power_kw: float, delta_t: float = 1.0) -> float:
        return max(0.0, min(power_kw, self.P_max)) * delta_t / self.eta_disc

    def available_charge_capacity_kwh(self) -> float:
        return max(0.0, self.soc_max * self.E_cap - self.soc)

    def available_discharge_capacity_kwh(self) -> float:
        return max(0.0, self.soc - self.soc_min * self.E_cap)

    def apply_self_discharge(self) -> None:
        self.soc = self.soc * (1.0 - self.sigma)

    def clamp_soc(self) -> None:
        self.soc = min(max(self.soc, self.soc_min * self.E_cap), self.soc_max * self.E_cap)

