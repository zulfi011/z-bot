from pathlib import Path

import yaml


def test_primary_and_control_exits_are_frozen_explicitly():
    path = Path("config/strategies/sol_15d_touch_v1.yaml")
    config = yaml.safe_load(path.read_text())
    primary = config["exit"]["primary"]
    control = config["exit"]["control"]

    assert primary["mode"] == "trailing_after_activation"
    assert primary["fixed_profit_target"]["enabled"] is False
    assert primary["protective_stop_pct_from_entry_fill"] == 4.0
    assert primary["trailing_stop"]["enabled"] is True
    assert primary["trailing_stop"]["activation_pct_from_entry_fill"] == 4.0
    assert primary["trailing_stop"]["giveback_of_open_profit_pct"] == 10.0

    assert control["mode"] == "fixed_profit_target"
    assert control["profit_target_pct_from_entry_fill"] == 4.0
    assert control["protective_stop_pct_from_entry_fill"] == 4.0
    assert control["trailing_stop"]["enabled"] is False
