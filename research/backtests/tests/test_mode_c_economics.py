from experiments.eth_canonical_v1.engine import CandidateTrade
from experiments.eth_canonical_v1.mode_c_economics import (
    failed_breakout_cooldown, fresh_band_after_failed_breakout,
    no_active_core_episode, one_lot_per_frozen_band,
)


def mode_c(entry=100, setup="band:1", episode="market:1"):
    return CandidateTrade(
        entry=entry, exit=entry + 10, exit_price=101.0, source="breakout",
        exit_code=1, candidate_id=f"mode-c:{entry}", setup_episode=setup,
        market_episode=episode,
    )


def lot(source="breakout", setup="band:1", episode="market:1",
        exit_kind="protective_stop", exit_index=90):
    return {"source": source, "setup_episode": setup, "market_episode": episode,
            "exit_kind": exit_kind, "exit_index": exit_index}


def test_mode_c_blocks_only_for_open_core_in_same_market_episode():
    candidate = mode_c()
    assert no_active_core_episode(candidate, [], [lot(source="dip")]) is not None
    assert no_active_core_episode(candidate, [], [lot(source="dip", episode="market:2")]) is None
    assert no_active_core_episode(candidate, [], [lot(source="breakout")]) is None


def test_one_lot_policy_uses_frozen_band_identity():
    candidate = mode_c()
    assert one_lot_per_frozen_band(candidate, [lot()], []) is not None
    assert one_lot_per_frozen_band(candidate, [lot(setup="band:2")], []) is None


def test_fresh_band_rule_requires_prior_protective_failure_in_same_band():
    candidate = mode_c()
    assert fresh_band_after_failed_breakout(candidate, [lot()], []) is not None
    assert fresh_band_after_failed_breakout(candidate, [lot(exit_kind="strategy_exit")], []) is None
    assert fresh_band_after_failed_breakout(candidate, [lot(setup="band:2")], []) is None


def test_failed_breakout_cooldown_is_mode_c_only_and_expires_at_boundary():
    policy = failed_breakout_cooldown(360)
    assert policy(mode_c(entry=449), [lot(exit_index=90)], []) is not None
    assert policy(mode_c(entry=450), [lot(exit_index=90)], []) is None
    dip = CandidateTrade(449, 460, 101.0, "dip", 1, "dip:449")
    assert policy(dip, [lot(exit_index=90)], []) is None
