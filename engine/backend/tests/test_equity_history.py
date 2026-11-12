from datetime import timedelta

from app.api.common import _equity_bucket


def test_equity_bucket_keeps_recent_accounts_detailed() -> None:
    assert _equity_bucket(timedelta(days=1)) == "5 minutes"
    assert _equity_bucket(timedelta(days=2)) == "5 minutes"


def test_equity_bucket_bounds_long_histories() -> None:
    assert _equity_bucket(timedelta(days=365)) == "1 day"
    assert _equity_bucket(timedelta(days=1095)) == "2 days"


def test_profit_summary_separates_costs_from_the_result():
    from decimal import Decimal as D
    from app.api.profit import _summarize
    rows = [{"net_pnl_usd": D("4"), "entry_fee_usd": D("0.08"), "exit_fee_usd": D("0.08"), "bnb_fees_usd": D("0.16"),
             "allocation_usd": D("100"), "duration_minutes": 60},
            {"net_pnl_usd": D("-2"), "entry_fee_usd": D("0.08"), "exit_fee_usd": D("0.08"), "bnb_fees_usd": D("0"),
             "allocation_usd": D("100"), "duration_minutes": 30}]
    summary = _summarize(rows)
    assert summary["net_pnl_usd"] == D("2") and summary["gross_pnl_usd"] == D("2.32")
    assert summary["fees_usd"] == D("0.32") and summary["fees_in_bnb_usd"] == D("0.16")
    assert summary["fees_in_usdt_usd"] == D("0.16")
    assert summary["wins"] == 1 and summary["losses"] == 1 and summary["win_rate_pct"] == 50
    assert summary["profit_factor"] == D("2")
    assert summary["best_usd"] == D("4") and summary["worst_usd"] == D("-2")


def test_profit_windows_cover_the_quick_ranges_and_custom_dates():
    from datetime import datetime, timezone
    from app.api.profit import _profit_window
    start, end, name = _profit_window("7d", None, None)
    assert name == "7d" and (end - start).days == 7
    custom_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    custom_end = datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert _profit_window("custom", custom_start, custom_end) == (custom_start, custom_end, "custom")
