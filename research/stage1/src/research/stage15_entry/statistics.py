"""Coverage, conditional outcomes, paired timing effects, and temporal checks."""

import numpy as np
import pandas as pd
from .outcomes import HORIZONS, WINDOWS, STOPS
from .signals import KEYS

GROUP_KEYS = [*KEYS, 'rule', 'wait_minutes', 'policy']


def block_interval(entered):
    """Exploratory paired-mean CI, resampling fixed seven-calendar-day blocks.

    This accounts for much within-week dependence but is not a multiplicity-
    adjusted significance test and does not prove independence across blocks.
    """
    if len(entered) < 30:
        return np.nan, np.nan, 0
    block = (entered.origin_signal_timestamp - pd.Timestamp('2024-09-01', tz='UTC')) // pd.Timedelta(days=7)
    frame = pd.DataFrame({'block': block, 'delta': entered.return_1440m_pct - entered.baseline_return_1440m_pct})
    stats = frame.groupby('block').delta.agg(['sum', 'count'])
    if len(stats) < 8:
        return np.nan, np.nan, len(stats)
    rng = np.random.default_rng(1502)
    indices = rng.integers(0, len(stats), size=(1000, len(stats)))
    boot = stats['sum'].to_numpy()[indices].sum(axis=1) / stats['count'].to_numpy()[indices].sum(axis=1)
    lower, upper = np.quantile(boot, [.025, .975])
    return lower, upper, len(stats)


def summarize(group, with_interval=False):
    entered = group.loc[group.entered]
    n = len(entered)
    row = {'eligible_episodes': len(group), 'entries': n,
           'confirmation_rate_pct': n/len(group)*100 if len(group) else np.nan,
           'unconfirmed_episodes': len(group)-n,
           'median_delay_minutes': entered.delay_minutes.median(),
           'median_entry_price_change_pct': entered.entry_price_change_pct.median()}
    for status in ['expired_wait_limit', 'cancelled_at_episode_exit', 'truncated_data_end', 'no_future_open']:
        row[f'{status}_count'] = int(group.status.eq(status).sum())
    for h in HORIZONS:
        values = entered[f'return_{h}m_pct']
        row[f'return_{h}m_mean_pct'] = values.mean()
        row[f'return_{h}m_median_pct'] = values.median()
    for w in WINDOWS:
        row[f'mae_{w}m_median_pct'] = entered[f'mae_{w}m_pct'].median()
        row[f'mfe_{w}m_median_pct'] = entered[f'mfe_{w}m_pct'].median()
    row['mae_1440m_p10_pct'] = entered.mae_1440m_pct.quantile(.1)
    row['mae_1440m_worst_pct'] = entered.mae_1440m_pct.min()
    mae, mfe = row['mae_1440m_median_pct'], row['mfe_1440m_median_pct']
    row['mfe_mae_ratio'] = mfe/abs(mae) if mae != 0 else np.nan
    row['positive_24h_pct'] = entered.return_1440m_pct.gt(0).mean()*100 if n else np.nan
    row['target_2_5_reach_pct'] = entered.target_2_5_reached.mean()*100 if n else np.nan
    row['target_median_minutes'] = entered.target_time_minutes.median()
    for stop in STOPS:
        counts = entered[f'first_{stop:g}'].value_counts()
        for outcome in ['target_first', 'stop_first', 'ambiguous', 'neither']:
            row[f'first_{stop:g}_{outcome}_count'] = int(counts.get(outcome, 0))
        decisive = counts.get('target_first',0) + counts.get('stop_first',0)
        row[f'first_{stop:g}_target_all_pct'] = counts.get('target_first',0)/n*100 if n else np.nan
        row[f'first_{stop:g}_target_decisive_pct'] = counts.get('target_first',0)/decisive*100 if decisive else np.nan
    baseline = entered.baseline_return_1440m_pct
    paired = entered.return_1440m_pct - baseline
    row['baseline_on_confirmed_mean_24h_pct'] = baseline.mean()
    row['baseline_on_confirmed_median_24h_pct'] = baseline.median()
    row['paired_mean_24h_change_pp'] = paired.mean()
    row['paired_median_24h_change_pp'] = paired.median()
    # An explicit per-opportunity normalization, NOT portfolio return. An
    # unconfirmed episode contributes zero; matched baseline still contributes
    # its observed return. This displays skipped-opportunity selection effects.
    row['cash_for_skips_mean_24h_pct'] = entered.return_1440m_pct.sum()/len(group) if len(group) else np.nan
    row['all_episode_baseline_mean_24h_pct'] = group.baseline_return_1440m_pct.mean()
    if with_interval:
        lo, hi, blocks = block_interval(entered)
        row.update({'paired_mean_ci95_low_pp': lo, 'paired_mean_ci95_high_pp': hi,
                    'paired_week_blocks': blocks})
    else:
        row.update({'paired_mean_ci95_low_pp': np.nan, 'paired_mean_ci95_high_pp': np.nan,
                    'paired_week_blocks': 0})
    return row


def build_summaries(candidates):
    eligible = candidates.loc[candidates.eligible].copy()
    main = eligible.loc[eligible.wait_minutes.isin([0, 30])]
    full, segments, monthly = [], [], []
    for period in ['all', 'earlier', 'later']:
        current = eligible if period == 'all' else eligible.loc[eligible.period.eq(period)]
        for key, group in current.groupby(GROUP_KEYS, observed=True, sort=True):
            full.append({**dict(zip(GROUP_KEYS, key)), 'period': period,
                         **summarize(group, with_interval=key[-2] == 30)})
        current_main = main if period == 'all' else main.loc[main.period.eq(period)]
        for column in ['approach', 'origin_regime']:
            for key, group in current_main.groupby([*GROUP_KEYS, column], observed=True, sort=True):
                segments.append({**dict(zip(GROUP_KEYS, key[:-1])), 'period': period,
                                 'segment_type': column, 'segment': key[-1], **summarize(group)})
    main = main.assign(month=main.origin_signal_timestamp.dt.strftime('%Y-%m'))
    for key, group in main.groupby([*GROUP_KEYS, 'month'], observed=True, sort=True):
        entered = group.loc[group.entered]
        monthly.append({**dict(zip(GROUP_KEYS, key[:-1])), 'month': key[-1],
                        'eligible_episodes': len(group), 'entries': len(entered),
                        'mean_24h_pct': entered.return_1440m_pct.mean(),
                        'median_24h_pct': entered.return_1440m_pct.median(),
                        'paired_mean_24h_change_pp': (entered.return_1440m_pct-entered.baseline_return_1440m_pct).mean()})
    return full, segments, monthly
