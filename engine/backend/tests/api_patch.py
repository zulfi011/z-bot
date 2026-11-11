"""Tests swap a dependency (settings, database, a reader) in every API module that uses it."""

from app.api import binance, coin_view, common, controls, dashboard, health, profit, session

API_MODULES = (common, session, controls, binance, health, coin_view, dashboard, profit)


def patch_api(monkeypatch, name: str, value) -> None:
    modules = [module for module in API_MODULES if hasattr(module, name)]
    assert modules, f"no API module uses {name}"
    for module in modules:
        monkeypatch.setattr(module, name, value)
