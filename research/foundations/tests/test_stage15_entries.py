"""Entry causality, confirmation expiry, and repriced outcome tests."""

import numpy as np
import pandas as pd
import pytest

from src.research.stage15_entry.signals import generate_candidates, reference_signal
from src.research.stage15_entry.outcomes import OutcomeEngine


def fixtures():
    times = pd.date_range('2025-01-01', periods=20, freq='5min', tz='UTC')
    candles = pd.DataFrame({'open_time': times, 'open': 99., 'high': 100.4, 'low': 98.8, 'close': 99.})
    candles.loc[0, ['open', 'high', 'low', 'close']] = [102., 102.2, 101.8, 102.]
    candles.loc[1, ['open', 'high', 'low', 'close']] = [100.2, 100.4, 98.8, 99.]
    candles.loc[2, ['open', 'high', 'low', 'close']] = [99., 100.4, 98.9, 100.2]
    for average in ['7d', '15d', '30d']:
        candles[f'average_{average}'] = 100.
    episode = pd.DataFrame([{'episode_id':'test', 'asset':'TEST', 'timeframe':'5m',
                            'average_type':'15d', 'touch_zone':.5, 'representative_event_id':'event',
                            'start_timestamp':times[1], 'left_censored':False}])
    return candles, episode


def policy(frame, rule, wait=30):
    return frame.loc[frame.rule.eq(rule) & frame.wait_minutes.eq(wait)].iloc[0]


def test_confirmation_available_only_after_close():
    candles, episodes = fixtures()
    results = generate_candidates(candles, episodes, '5m')
    row = policy(results, 'reclaim_average')
    assert row.entry_timestamp == candles.open_time.iloc[2] + pd.Timedelta('5min')
    assert row.delay_minutes == 5
    assert policy(results, 'first_touch', 0).entry_timestamp == candles.open_time.iloc[2]
    assert row.approach == 'from_above'


def test_close_above_is_distinct_from_crossing():
    candles, episodes = fixtures()
    candles.loc[1,'close'] = 100.1
    result = generate_candidates(candles, episodes, '5m')
    assert policy(result, 'close_above_average').delay_minutes == 0
    assert policy(result, 'reclaim_average').delay_minutes > 0 or pd.isna(policy(result, 'reclaim_average').entry_timestamp)


def test_first_touch_high_not_current_high():
    candles, episodes = fixtures()
    candles.loc[2, ['close','high']] = [100.6, 100.8]
    result = generate_candidates(candles, episodes, '5m')
    assert policy(result,'break_touch_high').delay_minutes == 5


def test_first_exit_can_confirm_and_then_cancels():
    candles, episodes = fixtures()
    candles.loc[2, ['open','high','low','close']] = [101., 102., 100.8, 101.8]
    result = generate_candidates(candles, episodes, '5m')
    assert policy(result, 'close_above_zone').delay_minutes == 5
    candles.loc[2, ['open','high','low','close']] = [98.,98.5,97.,97.5]
    candles.loc[3, ['open','high','low','close']] = [100.,102.,99.,101.]
    result = generate_candidates(candles, episodes, '5m')
    row = policy(result, 'close_above_zone')
    assert row.status == 'cancelled_at_episode_exit'
    assert pd.isna(row.entry_timestamp)


def test_wait_is_elapsed_minutes_and_inclusive():
    candles, episodes = fixtures()
    candles.loc[2, 'close'] = 99.
    candles.loc[4, 'close'] = 100.2
    result = generate_candidates(candles, episodes, '5m')
    assert policy(result, 'close_above_average',15).delay_minutes == 15
    candles.loc[4, 'close'] = 99.
    candles.loc[5, 'close'] = 100.2
    result = generate_candidates(candles, episodes, '5m')
    assert policy(result, 'close_above_average',15).status == 'expired_wait_limit'
    assert policy(result, 'close_above_average',30).delay_minutes == 20


def test_no_future_episode_end_used_and_prefix_invariance():
    candles, episodes = fixtures()
    a = generate_candidates(candles, episodes, '5m')
    episodes['end_timestamp'] = pd.Timestamp('2099-01-01',tz='UTC')
    candles.loc[8:, 'close'] = 500.
    b = generate_candidates(candles, episodes, '5m')
    mask = a.entry_timestamp.le(candles.open_time.iloc[7])
    pd.testing.assert_series_equal(a.loc[mask,'entry_timestamp'], b.loc[mask,'entry_timestamp'])
    prefix = generate_candidates(candles.iloc[:4], episodes, '5m')
    mask = a.entry_timestamp.le(candles.open_time.iloc[3])
    pd.testing.assert_series_equal(a.loc[mask,'entry_timestamp'], prefix.loc[mask,'entry_timestamp'])


def test_missing_grid_rejected():
    candles, episodes = fixtures()
    with pytest.raises(ValueError,match='grid'):
        generate_candidates(candles.drop(index=4), episodes, '5m')


def test_scalar_reference_all_rules():
    candles, episodes = fixtures()
    result = generate_candidates(candles, episodes, '5m')
    assert len(result) == 19
    for row in result.itertuples():
        expected = reference_signal(candles, 1,'15d',.5,row.rule,row.wait_minutes,'5m')
        assert (pd.isna(row.entry_timestamp) and expected is None) or row.entry_timestamp == expected


def raw_fixture():
    times = pd.date_range('2025-01-01', periods=3000, freq='1min', tz='UTC')
    return pd.DataFrame({'open_time':times, 'open':100.,'high':100.1,'low':99.9,'close':100.})


def test_outcome_uses_next_open_and_exact_horizon_including_entry_minute():
    raw=raw_fixture()
    raw.loc[10,['open','high','low','close']]=[101.,101.5,100.,101.]
    raw.loc[14,'close']=100.5
    engine=OutcomeEngine(raw)
    result=engine.calculate([raw.open_time.iloc[10]])
    assert result.entry_price.iloc[0]==101.
    assert result.return_5m_pct.iloc[0]==pytest.approx((100.5/101-1)*100)
    assert result.mae_60m_pct.iloc[0]==pytest.approx((99.9/101-1)*100)
    assert engine.validate_samples(result)==1


def test_same_minute_first_hit_is_ambiguous():
    raw=raw_fixture()
    raw.loc[10,['high','low']]=[103.,97.]
    engine=OutcomeEngine(raw)
    result=engine.calculate([raw.open_time.iloc[10]])
    assert result['first_2.5'].iloc[0]=='ambiguous'
    assert result.target_time_minutes.iloc[0]==1


def test_incomplete_window_and_nonexistent_entry_remain_unknown():
    raw=raw_fixture()
    engine=OutcomeEngine(raw)
    result=engine.calculate([raw.open_time.iloc[-1],raw.open_time.iloc[-1]+pd.Timedelta('1min')])
    assert not result.complete_24h.any()
    assert result.return_1440m_pct.isna().all()
    assert result.target_2_5_reached.isna().all()
    assert result['first_2.5'].eq('incomplete').all()
    assert result.entry_available.tolist()==[True,False]


def test_skipped_opportunities_and_paired_timing_are_distinct():
    from src.research.stage15_entry.statistics import summarize
    raw=raw_fixture()
    frame=OutcomeEngine(raw).calculate(raw.open_time.iloc[:3])
    frame['entered']=[True,False,True]
    frame['status']=['confirmed','expired_wait_limit','confirmed']
    frame['delay_minutes']=[5.,np.nan,10.]
    frame['entry_price_change_pct']=[1.,np.nan,-1.]
    frame['baseline_return_1440m_pct']=[5.,-10.,2.]
    frame['return_1440m_pct']=[4.,np.nan,3.]
    result=summarize(frame)
    assert result['entries']==2
    assert result['confirmation_rate_pct']==pytest.approx(200/3)
    assert result['return_1440m_mean_pct']==3.5
    assert result['baseline_on_confirmed_mean_24h_pct']==3.5
    assert result['paired_mean_24h_change_pp']==0.
    assert result['cash_for_skips_mean_24h_pct']==pytest.approx(7/3)
    assert result['all_episode_baseline_mean_24h_pct']==-1.


def test_week_block_interval_preserves_constant_paired_difference():
    from src.research.stage15_entry.statistics import block_interval
    frame=pd.DataFrame({'origin_signal_timestamp':pd.date_range('2025-01-01',periods=40,freq='3D',tz='UTC'),
                        'return_1440m_pct':2.,'baseline_return_1440m_pct':1.})
    low,high,blocks=block_interval(frame)
    assert low==high==1.
    assert blocks>=8
