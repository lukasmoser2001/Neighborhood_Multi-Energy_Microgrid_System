#A_grid_eb             : Utility Grid + Electric Boiler
#B_grid_gb             : Utility Grid + Gas Boiler
#C_grid_eb_pv_bess     : Utility Grid + Electric Boiler + PV + BESS
#D_grid_ashp_pv_bess_tess : Utility Grid + Air-Source Heat Pump + PV + BESS + TESS


# Each entry maps component keys (matching component_parameters.json) to
# their enabled state for the respective configuration.
CONFIGURATIONS: dict[str, dict[str, bool]] = {
    "A_grid_eb": {
        "utility_grid":     True,
        "pv_system":        False,
        "gas_boiler":       False,
        "electric_boiler":  True,
        "heat_pump_air":    False,
        "heat_pump_ground": False,
        "BESS":             False,
        "TESS":             False,
    },
    "B_grid_gb": {
        "utility_grid":     True,
        "pv_system":        False,
        "gas_boiler":       True,
        "electric_boiler":  False,
        "heat_pump_air":    False,
        "heat_pump_ground": False,
        "BESS":             False,
        "TESS":             False,
    },
    "C_grid_eb_pv_bess": {
        "utility_grid":     True,
        "pv_system":        True,
        "gas_boiler":       False,
        "electric_boiler":  True,
        "heat_pump_air":    False,
        "heat_pump_ground": False,
        "BESS":             True,
        "TESS":             False,
    },
    "D_grid_ashp_pv_bess_tess": {
        "utility_grid":     True,
        "pv_system":        True,
        "gas_boiler":       False,
        "electric_boiler":  False,
        "heat_pump_air":    True,
        "heat_pump_ground": False,
        "BESS":             True,
        "TESS":             True,
    },
}


def apply_configuration(base_config: dict, config_name: str) -> dict:
    if config_name not in CONFIGURATIONS:
        raise KeyError(
            f"Unknown configuration '{config_name}'. "
            f"Available: {list(CONFIGURATIONS.keys())}"
        )

    import copy
    cfg = copy.deepcopy(base_config)
    overrides = CONFIGURATIONS[config_name]

    for component_key, enabled_state in overrides.items():
        if component_key in cfg:
            cfg[component_key]["enabled"] = enabled_state

    return cfg
