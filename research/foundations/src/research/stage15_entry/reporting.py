"""Reproducible entry research tables and static figures."""

import numpy as np
import pandas as pd


def markdown(frame):
    rows=['| '+' | '.join(map(str,frame.columns))+' |','|'+'|'.join(['---']*len(frame.columns))+'|']
    for values in frame.itertuples(index=False,name=None):
        cells=[]
        for v in values:
            if isinstance(v,(float,np.floating)):
                cells.append('—' if pd.isna(v) else f'{v:.4f}')
            else:
                cells.append(str(v))
        rows.append('| '+' | '.join(cells)+' |')
    return '\n'.join(rows)


def write_report(path,summary,comparisons,effects,leaderboard,protected_count):
    main=summary.loc[summary.wait_minutes.isin([0,30])]
    primary=main.loc[main.asset.eq('SOLUSDT') & main.timeframe.eq('5m')
                     & main.average_type.eq('15d') & main.touch_zone.eq(.5)]
    columns=['rule','entries','confirmation_rate_pct','return_1440m_mean_pct','return_1440m_median_pct',
             'mae_1440m_median_pct','mfe_mae_ratio','first_2.5_target_decisive_pct','paired_mean_24h_change_pp']
    leading=leaderboard.loc[leaderboard.robustness_screen].head(12)
    leader_columns=['asset','timeframe','average_type','touch_zone','rule','entries_earlier','entries_later',
                    'return_1440m_mean_pct_earlier','return_1440m_mean_pct_later',
                    'return_1440m_median_pct_later','mae_1440m_median_pct_later']
    report=['# Stage 1.5 Step 2 — Entry Conditions', '', '## Objective and frozen design','',
        'Compare long-entry conditions across every one of the 81 Stage 1 configurations. '
        'SOL / 15D / 5m / ±0.5% is a reference, not a restriction. No stop, exit, regime-filter, or portfolio optimization is performed.', '',
        'Seven entry rules: first touch; bullish candle (close > open); close above the current average; '
        'reclaim (previous close <= previous average AND current close > current average); bullish close above the average; '
        'close above the zone upper boundary; close above the first touch candle high. '
        'All comparisons are strict. A close above the average need not be a crossing; reclaim does.', '',
        'Confirmation may occur on the first touch candle, a later touching candle, or the first non-touch candle. '
        'A pending confirmation is cancelled after that first exit candle. Wait limits are 15, 30 and 60 elapsed minutes '
        'after the first candle closes; 30 minutes is the prespecified main comparison. First touch has no wait. '
        'Daily average changes are used only when available; they can create an average-reclaim condition. '
        'No future episode end, peak, outcome, or best candle enters selection.', '',
        'There are 19 policies (one baseline plus six confirmations × three waits), or 1,539 setup-policy combinations. '
        'Each original episode has a candidate row under every policy, including cancellations and expiry.', '',
        '## Execution and comparable baseline', '',
        'A decision is available only after its timeframe candle closes. Entry uses the open of the next raw 1-minute candle, '
        'with zero latency/slippage as a research assumption. Forward horizons end at the close of minute H from entry; '
        'the first entry minute is included. MAE/MFE and diagnostic +2.5% target versus five fixed stops are recomputed '
        'from that actual entry price. Same-minute target/stop ordering remains ambiguous.', '',
        'The Step 1 baseline used the touch candle close and open-anchored forward returns. Therefore its old numbers '
        'must not be compared directly with delayed entries. step1_baseline_bridge.csv shows the timing/repricing '
        'difference on matched eligible episodes; the comparisons below use a newly computed first-touch baseline.', '',
        '## Cohorts, denominators, and robustness', '',
        'All policies share the same eligible origin episodes: exclude left-censored starts and require 60 minutes '
        'plus 24h of subsequent raw data. Earlier period ends before 2025-09-01 UTC; later begins on that date. '
        'Origins whose maximum evaluation window crosses the split are purged. This later period is a historical '
        'stability check, not untouched out-of-sample data: Stage 1 already examined the full history.', '',
        'Entry rate uses every eligible episode as denominator. Return/MAE/MFE/target metrics condition on entered episodes '
        'with complete 24h data. Both all-entry and decisive-only first-hit denominators are retained. '
        'Paired change compares the confirmed entry against first touch on exactly the same origin episodes, '
        'separating the effect of timing from selecting different episodes. Paired differences compare equal-duration '
        '24h windows from each entry, whose ending timestamps differ.', '',
        'The cash-for-skips mean assigns zero to unconfirmed opportunities to expose frequency loss; it is not a '
        'portfolio return or a capital model. Seven-calendar-day block bootstrap intervals for paired means are exploratory; '
        'they do not remove all dependence or adjust for testing many setups. Approach direction and origin regime are '
        'descriptive slices, not new entry filters. Monthly summaries and 15/60-minute waits check sensitivity.', '',
        '## Reference configuration — full eligible history', '',
        markdown(primary.loc[primary.period.eq('all'),columns].sort_values('rule')), '',
        '## Reference configuration — later period', '',
        markdown(primary.loc[primary.period.eq('later'),columns].sort_values('rule')), '',
        '## Cross-grid rule effects — later period, main wait', '',
        markdown(effects.loc[effects.period.eq('later') & effects.wait_minutes.isin([0,30]),
            ['rule','configurations','median_confirmation_rate_pct','configs_mean_return_higher',
             'configs_mae_improved','median_paired_mean_change_pp','positive_paired_ci95_count']]), '',
        'The higher-return count compares each rule with its own setup baseline. Positive paired CI counts are '
        'unadjusted exploratory diagnostics, not discoveries or proof of an edge.', '',
        '## Candidate screen across all assets, averages, timeframes, and zones', '',
        f'{int(leaderboard.robustness_screen.sum())} main-wait/baseline combinations pass the prespecified descriptive screen: '
        'at least 100 entries in each period and positive mean AND median 24h returns in both periods. '
        'The threshold controls tiny samples but is not a statistical power guarantee. The table is sorted by later-period '
        'mean return for inspection, not an optimality or tradability ranking.', '',
        markdown(leading[leader_columns]), '',
        '## Validation and preservation', '',
        'Synthetic tests cover signal timing, crossing versus level conditions, fixed first-touch-high references, '
        'exit-candle cancellation, elapsed wait limits, future-data invariance, exact next-open pricing, '
        'window endpoints, ambiguous barriers, and incomplete data. Every episode has 19 unique candidates. '
        'Per dataset, 40 sampled episodes × 19 policies are independently replayed with a scalar scanner; '
        '160 complete entry timestamps are checked against direct raw-price window scans. '
        'Signal bounds, cohort completeness, matched baseline coverage, exact Parquet and numeric CSV round trips are checked.', '',
        f'Before/after SHA-256 confirms {protected_count} protected Stage 1 and Step 1 files are unchanged. '
        'New outputs reside only under the Step 2 data/results directories. A completed run has SUCCESS.json.', '',
        '## Limitations and next decision', '',
        'These remain overlapping research observations. Nested zones, averages, timeframes and adjacent episodes '
        'share data; confirmation can select volatility and change the sample. Fees, slippage, latency, stop fills, '
        'position overlap, sizing and portfolio return are not modeled. Larger forward return or MFE alone does not '
        'establish an entry rule. Prefer improvements that survive matched-episode comparisons, downside checks, '
        'coverage, both historical periods, and nearby wait settings. Keep alternative configurations under consideration.', '',
        'This run stops at entry-condition analysis. No rule is promoted to a final strategy and no further refinement step is executed.', '',
        '## Step 2 decision', '',
        'Retain first-touch-at-next-open as the primary entry baseline. None of the tested confirmation rules '
        'showed a reliable improvement from waiting on matched episodes across the grid; every confirmation rule '
        'had a negative median paired 24h timing effect in the later period, and none produced a positive exploratory '
        'paired interval in any configuration. Bullish-candle confirmation is the only practical secondary candidate: '
        'it keeps roughly 95% of episodes, loses very little from waiting, and was slightly stronger in the later period '
        'for the reference setup. Stronger confirmations discarded many episodes and their attractive conditional '
        'subsets did not survive the matched timing comparison. Reclaim-average is rejected for this formulation due '
        'to very low coverage and weak reference results. This decision applies only to entry refinement; it does not '
        'establish profitability.', '',
        '## Reproduction and artifacts', '',
        '`python -B -m src.research.stage15_entry.run` (uses the repository Python environment; refuses existing output directories). '
        '`python -B -m pytest tests/test_stage15_entries.py` runs synthetic tests.', '',
        'summary.csv: all 1,539 combinations × three periods. comparisons.csv: own-baseline differences. '
        'rule_effects.csv: cross-grid counts and paired effects. leaderboard.csv: all main candidates and screening flags. '
        'segments.csv: approach/regime slices. monthly.csv: monthly outcomes. step1_baseline_bridge.csv: matched timing bridge. '
        'exclusions.csv and validation.csv: eligibility and audit results. Per-dataset Parquet files retain every candidate, '
        'including failed confirmations, signal/entry timestamps, entry price, and recomputed outcomes.', '']
    (path/'entry_report.md').write_text('\n'.join(report))
    plot_results(path,primary,effects,leaderboard)


def plot_results(path,primary,effects,leaderboard):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'figure.dpi':140})
    figure,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    pivot=primary.pivot(index='rule',columns='period',values='return_1440m_mean_pct')
    pivot[['earlier','later']].plot.barh(ax=axes[0],color=['#6e9dbd','#1b6b54'])
    axes[0].axvline(0,color='black',linewidth=.7)
    axes[0].set_xlabel('Mean 24h forward return (%)')
    axes[0].set_ylabel('')
    axes[0].set_title('Reference setup: earlier vs later')
    current=primary.loc[primary.period.eq('all')].set_index('rule').reindex(pivot.index)
    current.confirmation_rate_pct.plot.barh(ax=axes[1],color='#1b6b54')
    axes[1].set_xlabel('Confirmed entries / eligible episodes (%)')
    axes[1].set_ylabel('')
    axes[1].set_xlim(0,105)
    axes[1].set_title('Reference setup: confirmation coverage')
    figure.suptitle('SOL / 15D / 5m / ±0.5% — first touch vs 30-minute confirmations')
    figure.savefig(path/'reference_entry_comparison.png')
    plt.close(figure)
    figure,axis=plt.subplots(figsize=(10,6),layout='constrained')
    frame=leaderboard.loc[leaderboard.enough_samples]
    for asset,color in [('BTCUSDT','#dd9b26'),('ETHUSDT','#7272b0'),('SOLUSDT','#237e65')]:
        part=frame.loc[frame.asset.eq(asset)]
        axis.scatter(part.mae_1440m_median_pct_later,part.return_1440m_mean_pct_later,
                     alpha=.45,s=30,label=asset,color=color)
    axis.axhline(0,color='black',linewidth=.7)
    axis.set_xlabel('Later-period median MAE (%) — farther right means less downside')
    axis.set_ylabel('Later-period mean 24h return (%)')
    axis.set_title('All main entry candidates with ≥100 entries in each period')
    axis.legend()
    figure.savefig(path/'all_candidates_return_downside.png')
    plt.close(figure)
