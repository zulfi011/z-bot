"""The dip and the quiet-band breakout can be switched off per coin; they start on."""

from app.domain.paper_execution import CoinAllocation


def allocation(*entries):
    return CoinAllocation(frozenset(entries))


def test_new_coins_start_with_the_core_on():
    default = CoinAllocation.default()
    assert default.allows("signal") and default.allows("breakout")


def test_switching_the_dip_off_blocks_dip_signals_only():
    no_dip = allocation("breakout", "pullback")
    assert not no_dip.allows("signal")
    assert no_dip.allows("breakout") and no_dip.allows("pullback")


def test_switching_the_breakout_off_blocks_breakouts_only():
    no_break = allocation("dip")
    assert not no_break.allows("breakout") and no_break.allows("signal")


def test_buy_now_is_never_blocked_by_a_switch():
    assert allocation().allows("manual")
