"""Run Step 2 entry research without modifying Stage 1 or Step 1 artifacts."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.research.stage15.validation import sha256
from .signals import KEYS, RULES, WAITS, generate_candidates, reference_signal, require
from .outcomes import OutcomeEngine
from .statistics import GROUP_KEYS, build_summaries

ROOT = Path(__file__).resolve().parents[3]
RUN = 'step2_entry_conditions_v1'
DATA = ROOT / 'data/research/stage15' / RUN
RESULTS = ROOT / 'results/stage15' / RUN
STEP1 = ROOT / 'data/research/stage15/step1_consecutive_touch_first_v1'
SPLIT = pd.Timestamp('2025-09-01', tz='UTC')


def protected_snapshot():
    paths=[]
    for folder in ['data','results','src','config','experiments']:
        for p in (ROOT/folder).rglob('*'):
            if not p.is_file() or RUN in p.parts or 'stage15_entry' in p.parts or '__pycache__' in p.parts:
                continue
            if p.name == 'v1_stage15_step2_entries.yaml':
                continue
            paths.append(p)
    paths += [ROOT/'AGENTS.md',ROOT/'README.md',ROOT/'V1_Stage1_Historical_Engine_Results.md']
    return {str(p.relative_to(ROOT)):{'size':p.stat().st_size,'sha256':sha256(p)} for p in sorted(set(paths))}


def save_table(name, table):
    path=RESULTS/f'{name}.csv'
    table.to_csv(path,index=False)
    loaded=pd.read_csv(path)
    pd.testing.assert_frame_equal(table.reset_index(drop=True),loaded,check_dtype=False,check_exact=False,rtol=1e-9,atol=1e-9)


def validate_signals(candles, episodes, candidates, count=40):
    require(len(candidates)==len(episodes)*19,'Missing candidate/policy combinations')
    require(candidates.groupby('episode_id').size().eq(19).all(),'Unbalanced policy population')
    confirmed=candidates.loc[candidates.status.eq('confirmed')]
    delta=pd.Timedelta(candidates.timeframe.iloc[0])
    require((confirmed.entry_timestamp==confirmed.signal_candle_timestamp+delta).all(),'Premature execution')
    require(confirmed.delay_minutes.ge(0).all() and confirmed.delay_minutes.le(confirmed.wait_minutes).all(),'Wait bounds violated')
    sample=episodes.sample(n=min(count,len(episodes)),random_state=1502)
    lookup=pd.DatetimeIndex(candles.open_time)
    checks=0
    for episode in sample.itertuples():
        start=lookup.get_loc(episode.start_timestamp)
        for candidate in candidates.loc[candidates.episode_id.eq(episode.episode_id)].itertuples():
            expected=reference_signal(candles,start,episode.average_type,episode.touch_zone,
                                      candidate.rule,candidate.wait_minutes,episode.timeframe)
            require((expected is None and pd.isna(candidate.entry_timestamp)) or expected==candidate.entry_timestamp,'Scalar replay mismatch')
            checks+=1
    return checks


def baseline_bridge(base, tag, asset):
    old=pd.read_parquet(STEP1/asset/f'{tag}_episode_outcomes.parquet',columns=[
        'event_id','price','return_24h_pct','max_downside_24h_pct','max_upside_24h_pct'])
    merged=base.merge(old,left_on='representative_event_id',right_on='event_id',validate='one_to_one')
    require(len(merged)==len(base),'Step 1 baseline coverage mismatch')
    rows=[]
    for key,group in merged.groupby(KEYS,observed=True):
        common=group.loc[group.eligible]
        rows.append({**dict(zip(KEYS,key)),'step1_episode_count':len(group),'common_eligible_episodes':len(common),
            'step1_common_mean_24h_pct':common.return_24h_pct.mean(),
            'step2_first_touch_common_mean_24h_pct':common.return_1440m_pct.mean(),
            'step1_common_median_24h_pct':common.return_24h_pct.median(),
            'step2_first_touch_common_median_24h_pct':common.return_1440m_pct.median(),
            'median_next_open_vs_touch_close_pct':((common.entry_price/common.price-1)*100).median(),
            'step1_common_mae_median_pct':common.max_downside_24h_pct.median(),
            'step2_first_touch_common_mae_median_pct':common.mae_1440m_pct.median()})
    return rows


def derive_tables(summary):
    main=summary.loc[summary.wait_minutes.isin([0,30])].copy()
    baseline=summary.loc[summary.rule.eq('first_touch'),[*KEYS,'period','return_1440m_mean_pct','return_1440m_median_pct','mae_1440m_median_pct','mfe_mae_ratio']]
    baseline=baseline.rename(columns={c:f'baseline_{c}' for c in baseline if c not in [*KEYS,'period']})
    compared=summary.merge(baseline,on=[*KEYS,'period'],validate='many_to_one')
    for c in ['return_1440m_mean_pct','return_1440m_median_pct','mae_1440m_median_pct','mfe_mae_ratio']:
        compared[f'change_{c}']=compared[c]-compared[f'baseline_{c}']
    effects=[]
    for key,group in compared.groupby(['rule','wait_minutes','period'],observed=True):
        effects.append({'rule':key[0],'wait_minutes':key[1],'period':key[2],
            'configurations':len(group),'median_confirmation_rate_pct':group.confirmation_rate_pct.median(),
            'configs_mean_return_higher':int(group.change_return_1440m_mean_pct.gt(0).sum()),
            'configs_median_return_higher':int(group.change_return_1440m_median_pct.gt(0).sum()),
            'configs_mae_improved':int(group.change_mae_1440m_median_pct.gt(0).sum()),
            'median_mean_return_change_pp':group.change_return_1440m_mean_pct.median(),
            'median_paired_mean_change_pp':group.paired_mean_24h_change_pp.median(),
            'positive_paired_ci95_count':int(group.paired_mean_ci95_low_pp.gt(0).sum())})
    earlier=main.loc[main.period.eq('earlier')].drop(columns='period')
    later=main.loc[main.period.eq('later')].drop(columns='period')
    board=earlier.merge(later,on=GROUP_KEYS,suffixes=('_earlier','_later'),validate='one_to_one')
    board['enough_samples']=board.entries_earlier.ge(100)&board.entries_later.ge(100)
    board['positive_both_means']=board.return_1440m_mean_pct_earlier.gt(0)&board.return_1440m_mean_pct_later.gt(0)
    board['positive_both_medians']=board.return_1440m_median_pct_earlier.gt(0)&board.return_1440m_median_pct_later.gt(0)
    board['robustness_screen']=board.enough_samples&board.positive_both_means&board.positive_both_medians
    board=board.sort_values(['robustness_screen','return_1440m_mean_pct_later'],ascending=[False,False]).reset_index(drop=True)
    return compared,pd.DataFrame(effects),board


def run():
    config=yaml.safe_load((ROOT/'config/experiments/v1_stage15_step2_entries.yaml').read_text())
    require(config['entry']['confirmations']==RULES and config['entry']['wait_minutes']==WAITS,'Unsupported rule grid')
    require(config['entry']['main_wait_minutes']==30 and config['robustness']['split_utc']=='2025-09-01'
            and config['robustness']['common_tail_minutes']==1500,'Unsupported evaluation settings')
    require(not DATA.exists() and not RESULTS.exists(),'Run already exists; refusing overwrite')
    print('Hashing protected Stage 1 and Step 1 artifacts...',flush=True)
    before=protected_snapshot()
    DATA.mkdir(parents=True,exist_ok=False)
    RESULTS.mkdir(parents=True,exist_ok=False)
    (RESULTS/'source_manifest_before.json').write_text(json.dumps(before,indent=2)+'\n')
    (RESULTS/'experiment.json').write_text(json.dumps(config,indent=2)+'\n')
    full,segments,monthly,bridges,checks,exclusions=[],[],[],[],[],[]
    source=yaml.safe_load((ROOT/'config/experiments/v1_stage1.yaml').read_text())
    for asset in source['data']['assets']:
        print(f'{asset}: building raw price query engine',flush=True)
        raw=pd.read_parquet(ROOT/f'data/raw/{asset}/{asset}_1m.parquet',columns=['open_time','open','high','low','close'])
        engine=OutcomeEngine(raw)
        data_end=engine.times[-1]+pd.Timedelta('1min')
        for timeframe in source['research']['timeframes']:
            tag=f'{asset}_{timeframe}'
            print(f'{tag}: generating all entry policies',flush=True)
            candles=pd.read_parquet(ROOT/f'data/processed/{asset}/{tag}_with_averages.parquet',columns=[
                'open_time','open','high','low','close','average_7d','average_15d','average_30d'])
            # Retrospective episode ends/lengths deliberately never enter the signal generator.
            episodes=pd.read_parquet(STEP1/asset/f'{tag}_episodes.parquet',columns=[
                'episode_id',*KEYS,'representative_event_id','start_timestamp','left_censored'])
            candidates=generate_candidates(candles,episodes,timeframe)
            replay=validate_signals(candles,episodes,candidates)
            print(f'{tag}: repricing {candidates.entry_timestamp.nunique():,} unique entry timestamps',flush=True)
            outcomes=engine.calculate(candidates.entry_timestamp.dropna())
            scans=engine.validate_samples(outcomes)
            candidates=candidates.merge(outcomes,on='entry_timestamp',how='left',validate='many_to_one')
            available=candidates.entry_available.eq(True)
            candidates.loc[candidates.status.eq('confirmed') & ~available,'status']='no_future_open'
            candidates['entered']=candidates.status.eq('confirmed') & available
            origin=candidates.origin_signal_timestamp
            matured=origin+pd.Timedelta(minutes=1500)<=data_end
            crossing=origin.lt(SPLIT)&(origin+pd.Timedelta(minutes=1500)>SPLIT)
            candidates['period']=np.where(origin<SPLIT,'earlier','later')
            candidates['eligible']=~candidates.left_censored & matured & ~crossing
            candidates['exclusion_reason']=np.select([candidates.left_censored,~matured,crossing],
                ['left_censored','incomplete_common_tail','split_crossing'],default='eligible')
            require(candidates.loc[candidates.eligible & candidates.entered,'complete_24h'].eq(True).all(),'Incomplete scored entry')
            base=candidates.loc[candidates.rule.eq('first_touch')].copy()
            pair=base[['episode_id','entry_price','return_1440m_pct']].rename(columns={
                'entry_price':'baseline_entry_price','return_1440m_pct':'baseline_return_1440m_pct'})
            candidates=candidates.merge(pair,on='episode_id',validate='many_to_one')
            candidates['entry_price_change_pct']=(candidates.entry_price/candidates.baseline_entry_price-1)*100
            for reason,group in base.groupby('exclusion_reason'):
                exclusions.append({'asset':asset,'timeframe':timeframe,'reason':reason,'episodes':len(group)})
            bridges.extend(baseline_bridge(base,tag,asset))
            out=DATA/asset
            out.mkdir(exist_ok=True)
            path=out/f'{tag}_entry_candidates.parquet'
            candidates.to_parquet(path,index=False)
            persisted=pd.read_parquet(path)
            pd.testing.assert_frame_equal(candidates,persisted,check_exact=True)
            require(not persisted.duplicated(['episode_id','policy']).any(),'Saved duplicate candidates')
            require(persisted.loc[persisted.eligible,'baseline_return_1440m_pct'].notna().all(),'Missing paired baseline')
            print(f'{tag}: summarizing coverage, outcomes, paired effects, and historical stability',flush=True)
            tables=build_summaries(persisted)
            full.extend(tables[0]);segments.extend(tables[1]);monthly.extend(tables[2])
            checks.append({'dataset':tag,'pass':True,'scalar_signal_replays':replay,
                           'direct_raw_outcome_scans':scans,'candidate_rows':len(candidates),
                           'episodes':len(episodes),'exact_parquet_roundtrip':True})
            del candles,episodes,candidates,persisted,base,pair,outcomes
        del engine,raw
    summary=pd.DataFrame(full)
    require(len(summary)==81*19*3,'Missing configurations/policies/periods')
    compared,effects,leaderboard=derive_tables(summary)
    for name,frame in [('summary',summary),('comparisons',compared),('rule_effects',effects),
                       ('leaderboard',leaderboard),('segments',pd.DataFrame(segments)),
                       ('monthly',pd.DataFrame(monthly)),('step1_baseline_bridge',pd.DataFrame(bridges)),
                       ('exclusions',pd.DataFrame(exclusions)),('validation',pd.DataFrame(checks))]:
        save_table(name,frame)
    print('Checking protected file hashes...',flush=True)
    after=protected_snapshot()
    require(before==after,'Protected Stage 1 / Step 1 artifacts changed')
    (RESULTS/'source_manifest_after.json').write_text(json.dumps(after,indent=2)+'\n')
    from .reporting import write_report
    write_report(RESULTS,summary,compared,effects,leaderboard,len(before))
    (RESULTS/'SUCCESS.json').write_text(json.dumps({'step':2,'scope':'entry_conditions_only',
        'configurations':81,'policies':19,'candidate_rows':int(sum(c['candidate_rows'] for c in checks)),
        'protected_files_unchanged':len(before),'validation':'PASS'},indent=2)+'\n')
    print('Completed: '+str(RESULTS/'entry_report.md'),flush=True)


if __name__=='__main__':
    run()
