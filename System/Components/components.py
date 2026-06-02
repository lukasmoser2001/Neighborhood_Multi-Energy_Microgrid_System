# Utility grid component
class UtilityGrid:
    def __init__(self, config: dict):
        self.enabled = config.get("enabled", True)
        self.electricity_price_eur_per_kwh = config.get("electricity_price_eur_per_kwh", 0.1793)
        self.emission_factor_kg_per_kwh = config.get("emission_factor_kg_per_kwh", 0.020)

    def get_cost_eur(self, electricity_kwh: float) -> float:
        return electricity_kwh * self.electricity_price_eur_per_kwh

    def get_emissions_kg(self, electricity_kwh: float) -> float:
        return electricity_kwh * self.emission_factor_kg_per_kwh


# PV system component
class PVSystem:
    def __init__(self, config: dict):
        self.enabled = config.get("enabled", True)
        self.i_stc = config.get("i_stc_w_m2", 1000.0)
        self.t_stc = config.get("t_stc_c", 25.0)
        self.i_ref = config.get("i_ref_w_m2", 800.0)
        self.t_ref = config.get("t_ref_c", 20.0)
        self.t_nom = config.get("t_nom_c", 44.0)
        self.beta = config.get("beta_per_c", 0.0024)
        self.panel_area_m2 = config.get("panel_area_m2", 2.08)
        self.panels_per_household = config.get("panels_per_household", 6)
        self.power_density_w_m2 = config.get("power_density_w_m2", 224)
        self.capex_per_panel_eur = config.get("annualized_capital_cost_per_panel_eur", 15.74)
        self.om_cost_per_kwh = config.get("o_and_m_cost_per_kwh_eur", 0.01)
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
class GasBoiler:
    def __init__(self, config: dict):
        self.enabled = config.get("enabled", True)
        self.lcoh_eur_per_kwh = config.get("lcoh_eur_per_kwh", 0.13)
        self.emission_factor_kg_per_kwh = config.get("emission_factor_kg_per_kwh", 0.02)

    def get_cost_eur(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.lcoh_eur_per_kwh

    def get_emissions_kg(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.emission_factor_kg_per_kwh


# Electric boiler component
class ElectricBoiler:
    def __init__(self, config: dict):
        self.enabled = config.get("enabled", False)
        self.efficiency = config.get("efficiency", 0.95)
        self.lcoh_eur_per_kwh = config.get("lcoh_eur_per_kwh", 0.15)
        self.emission_factor_kg_per_kwh = config.get("emission_factor_kg_per_kwh", 0.0)

    def get_electricity_demand_kwh(self, thermal_kwh: float) -> float:
        return thermal_kwh / self.efficiency

    def get_cost_eur(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.lcoh_eur_per_kwh

    def get_emissions_kg(self, thermal_kwh: float) -> float:
        return thermal_kwh * self.emission_factor_kg_per_kwh

