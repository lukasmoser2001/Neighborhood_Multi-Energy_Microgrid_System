"""
configurations.py — Predefined system configurations for the Neighborhood Multi-Energy Microgrid.

Each configuration is a dict that overrides the ``enabled`` flag for every component
in the base parameter set loaded from component_parameters.json.  All other
parameters (costs, efficiencies, capacities, etc.) remain unchanged and are
taken directly from the JSON file.

The ``enabled`` field has been removed from component_parameters.json.
All activation logic is now centralised here, making it the single source
of truth for which components are active in a given scenario.

Available configurations
------------------------
A_grid_eb             : Utility Grid + Electric Boiler
B_grid_gb             : Utility Grid + Gas Boiler
C_grid_eb_pv_bess     : Utility Grid + Electric Boiler + PV + BESS
D_grid_ashp_pv_bess_tess : Utility Grid + Air-Source Heat Pump + PV + BESS + TESS
"""

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
    """
    Return a deep copy of *base_config* with ``enabled`` flags injected
    according to the named predefined configuration.

    Parameters
    ----------
    base_config : dict
        Full parameter dict loaded from component_parameters.json.
        The JSON no longer carries ``enabled`` keys; those are supplied
        entirely by this function.
    config_name : str
        Key from CONFIGURATIONS (e.g. ``"A_grid_eb"``).

    Returns
    -------
    dict
        Modified parameter dict ready for ``apply_component_parameters()``.

    Raises
    ------
    KeyError
        If *config_name* is not found in CONFIGURATIONS.
    """
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
