"""Builds one coin's page: open lots, the trend line, the breakout band, pullback and add-on state."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text

from app.api.common import CHART_INTERVALS, ZERO
from app.core.strategy import COIN_NAMES
from app.domain import trend
from app.domain.consolidation import ConsolidationConfig, build_bars, zone_before
from app.domain.execution import MODULES, CoinAllocation, ExecutionConfig, ExitSignal, FeeContext, Position, fill_exit
from app.domain.pullback import PullbackConfig, PullbackState
from app.domain.pullback import step as pullback_step
from app.domain.pyramid import PyramidConfig
from app.services.account import affordable_lot, coin_label, read_allocation, read_pot, read_trading_enabled


def _close_estimate(row: dict, config: ExecutionConfig, context: FeeContext, mark: Decimal, now: datetime) -> dict:
    """What closing this lot right now would return, after exit slippage and fee."""
    position = Position(row["position_id"], row["entry_time"], row["raw_entry_price"], row["entry_fill_price"],
                        row["quantity"], row["allocation_usd"], row["entry_fee_usd"], row["entry_fee_asset"],
                        symbol=row["symbol"])
    fill = fill_exit(position, ExitSignal("manual_close", mark, now, 0), config, context)
    return {"price": mark, "exit_fill_price": fill.fill_price, "fee_usd": fill.fee.usd, "fee_asset": fill.fee.asset,
            "slippage_usd": fill.slippage_usd, "cash_back_usd": fill.cash_in_usd, "net_pnl_usd": fill.net_pnl_usd,
            "net_return_pct": fill.net_return_pct}


def _position_view(row: dict, config: ExecutionConfig, mark: Decimal | None,
                   context: FeeContext | None = None, now: datetime | None = None) -> dict:
    fill = row["entry_fill_price"]
    # The stop parked on Binance, as stored when it was placed (rounded to the price tick); the formula is only a
    # fallback for a lot whose stop order could not be placed.
    stop = row.get("stop_price") or fill * (1 - config.stop_pct / 100)
    activation = fill * (1 + config.trail_activation_pct / 100)
    peak = row["peak_price"] or fill
    trend_ride = bool(row.get("trend_exit_active")) and config.trend_exit_ema_minutes is not None
    # A trend-ride lot has no giveback level: it is held until a minute closes below the trend line.
    trail = (fill + (peak - fill) * (1 - config.trail_giveback_pct / 100)
             if row["trailing_active"] and not trend_ride else None)
    value = row["quantity"] * mark if mark else None
    cost = row["allocation_usd"] + (row["entry_fee_usd"] if row["entry_fee_asset"] == "BNB" else ZERO)
    return {
        **row, "coin": coin_label(row["symbol"]), "current_price": mark, "market_value_usd": value,
        "unrealized_pnl_usd": value - cost if value is not None else None,
        "unrealized_pct": (value / cost - 1) * 100 if value is not None and cost else None,
        "stop_price": stop, "activation_price": activation, "trail_price": trail,
        "exit_mode": "trend" if trend_ride else "giveback",
        "trend_exit_pending": bool(row.get("trend_exit_pending")),
        "trend_ema_minutes": config.trend_exit_ema_minutes if trend_ride else None,
        "stop_pct": config.stop_pct, "trail_activation_pct": config.trail_activation_pct,
        "trail_giveback_pct": config.trail_giveback_pct,
        "distance_to_stop_pct": (mark / stop - 1) * 100 if mark else None,
        "distance_to_activation_pct": (activation / mark - 1) * 100 if mark and not row["trailing_active"] else None,
        "activation_progress_pct": max(ZERO, min(Decimal("100"), (mark - fill) / (activation - fill) * 100))
        if mark and not row["trailing_active"] else Decimal("100"),
        "close_estimate": _close_estimate(row, config, context, mark, now) if mark and context and now else None,
    }


def _trend_line(connection, symbol: str, chart: list[dict], ema_minutes: int, bucket_minutes: int) -> None:
    """Add the trend line to each chart bucket, as the value at the bucket's last minute.

    The EMA is defined on 1-minute closes, so it is rebuilt here from the raw candles with a warm-up in front
    of the visible range. Slow charts are skipped: a 16-hour line on a 1-day chart says nothing, and reading
    months of minutes would make the dashboard crawl.
    """
    if not chart or bucket_minutes > 60:
        return
    warmup = ema_minutes * 5
    rows = connection.execute(
        text("""SELECT open_time, close FROM candles_1m
                WHERE symbol=:s AND open_time >= :start - make_interval(mins => :warmup)
                ORDER BY open_time"""),
        {"s": symbol, "start": chart[0]["open_time"], "warmup": warmup},
    ).all()
    if not rows:
        return
    span = timedelta(minutes=bucket_minutes)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    by_bucket: dict[datetime, Decimal] = {}
    value = None
    for open_time, close in rows:
        value = trend.advance(value, Decimal(close), ema_minutes)
        bucket = epoch + ((open_time - epoch) // span) * span
        by_bucket[bucket] = value
    for row in chart:
        row["trend_line"] = by_bucket.get(row["open_time"])


class _RawCandle:
    __slots__ = ("open_time", "high", "low", "close")

    def __init__(self, open_time, high, low, close):
        self.open_time, self.high, self.low, self.close = open_time, high, low, close


def _consolidation_band(connection, symbol: str, chart: list[dict], rule: ConsolidationConfig,
                        bucket_minutes: int) -> None:
    """Mark every chart bucket that sat inside a quiet band, so the zone can be drawn where it happened.

    The band is the one the rule was watching at that moment: the `zone_bars` bars before the current one. A
    bucket gets no band when the price was not quiet then, which is what makes the shading meaningful.
    """
    if not chart:
        return
    warmup = rule.chart_minutes * (rule.zone_bars + 1)
    rows = connection.execute(
        text("""SELECT open_time, high, low, close FROM candles_1m
                WHERE symbol=:s AND open_time >= :start - make_interval(mins => :warmup)
                ORDER BY open_time"""),
        {"s": symbol, "start": chart[0]["open_time"], "warmup": warmup},
    ).all()
    bars = build_bars([_RawCandle(*row) for row in rows], rule.chart_minutes)
    span = timedelta(minutes=rule.chart_minutes)
    bands = {}
    for index, bar in enumerate(bars):
        zone = zone_before(bars, index, rule)
        if zone and zone.width_pct <= rule.maximum_zone_pct:
            bands[bar.open_time] = zone
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    for row in chart:
        bar_start = epoch + ((row["open_time"] - epoch) // span) * span
        zone = bands.get(bar_start)
        row["zone_top"] = zone.top if zone else None
        row["zone_bottom"] = zone.bottom if zone else None


def _consolidation_view(connection, symbol: str, strategy_id: str, rule: ConsolidationConfig | None,
                        mark) -> dict | None:
    """The quiet-band breakout right now: the band being watched, how quiet it is, and any break waiting out its confirmation."""
    if rule is None:
        return None
    stored = connection.execute(
        text("SELECT value FROM engine_state WHERE key=:key"), {"key": f"consolidation:{symbol}"}
    ).scalar_one_or_none() or {}
    pending = connection.execute(
        text("""SELECT signal_id, signal_time, details FROM signals
                WHERE strategy_id=:strategy AND status='pending_confirmation'
                  AND details->>'kind'='consolidation'
                ORDER BY signal_time DESC LIMIT 1"""),
        {"strategy": strategy_id},
    ).mappings().one_or_none()
    top = Decimal(stored["zone_top"]) if stored.get("zone_top") else None
    bottom = Decimal(stored["zone_bottom"]) if stored.get("zone_bottom") else None
    width = Decimal(stored["zone_width_pct"]) if stored.get("zone_width_pct") else None
    quiet = bool(stored.get("quiet"))
    return {
        "chart_minutes": rule.chart_minutes, "zone_bars": rule.zone_bars,
        "zone_hours": rule.chart_minutes * rule.zone_bars / 60,
        "maximum_zone_pct": rule.maximum_zone_pct, "confirmation_wait_minutes": rule.confirmation_wait_minutes,
        # The breakout's own exit numbers: on AAVE the dip now arms later than a break does, so the page says both.
        "stop_pct": rule.stop_pct, "trail_activation_pct": rule.trail_activation_pct,
        "trail_giveback_pct": rule.trail_giveback_pct,
        "quiet": quiet, "zone_top": top, "zone_bottom": bottom, "zone_width_pct": width,
        "zone_since": stored.get("zone_since"),
        # How far the band still has to tighten before a break from it would be traded.
        "width_needed_pct": None if width is None else max(ZERO, width - rule.maximum_zone_pct),
        "distance_to_break_pct": None if (top is None or not mark) else (top / mark - 1) * 100,
        "state": ("breaking" if quiet and top is not None and mark and mark > top
                  else "quiet" if quiet else "too_wide" if width is not None else "warming_up"),
        "pending_break": None if pending is None else {
            "signal_id": pending["signal_id"], "broke_at": pending["signal_time"],
            "confirm_at": pending["details"].get("confirm_at"),
            "zone_top": Decimal(pending["details"]["zone_top"]) if pending["details"].get("zone_top") else None,
        },
        "checked_at": stored.get("checked_at"), "breakouts_seen": stored.get("breakouts_seen"),
    }


def _day_regimes(connection, symbol: str, start: datetime) -> dict[datetime, str]:
    """The trend for every UTC day from `start`, as the daily averages effective that day define it."""
    rows = connection.execute(
        text("""SELECT effective_at, average_7d, average_15d, average_30d FROM daily_averages
                WHERE symbol=:s AND effective_at >= date_trunc('day', CAST(:start AS timestamptz))"""),
        {"s": symbol, "start": start},
    ).all()
    regimes = {}
    for day, a7, a15, a30 in rows:
        regimes[day] = (None if None in (a7, a15, a30) else
                        "bullish" if a7 > a15 > a30 else "bearish" if a7 < a15 < a30 else "neutral")
    return regimes


def _pullback_overlay(connection, symbol: str, chart: list[dict], rule: PullbackConfig, bucket_minutes: int) -> None:
    """The pullback line on each bucket, and whether a pullback was armed there.

    "Armed" means the rule would buy the next close above the line: inside an uptrend, and already below it for
    the full dwell. That is the stretch worth seeing on the chart - where the third way in was loaded. It is
    rebuilt from 1-minute candles with the same `step` the live rule uses, after a 5-span warm-up. Daily charts
    are skipped: a 24-hour line on 1-day candles would read months of minutes to say nothing.
    """
    if not chart or bucket_minutes > 240:
        return
    warmup = rule.ema_minutes * 5
    rows = connection.execute(
        text("""SELECT open_time, close FROM candles_1m
                WHERE symbol=:s AND open_time >= :start - make_interval(mins => :warmup)
                ORDER BY open_time"""),
        {"s": symbol, "start": chart[0]["open_time"], "warmup": warmup},
    ).all()
    if not rows:
        return
    regimes = _day_regimes(connection, symbol, chart[0]["open_time"])
    span = timedelta(minutes=bucket_minutes)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    lines: dict[datetime, Decimal] = {}
    armed: set[datetime] = set()
    state = PullbackState()
    for open_time, close in rows:
        state, _ = pullback_step(state, open_time, Decimal(close), rule)
        bucket = epoch + ((open_time - epoch) // span) * span
        lines[bucket] = state.ema
        day = open_time.replace(hour=0, minute=0, second=0, microsecond=0)
        if state.below_minutes >= rule.dwell_minutes and (not rule.requires_uptrend or regimes.get(day) == "bullish"):
            armed.add(bucket)
    for row in chart:
        row["pullback_line"] = lines.get(row["open_time"])
        row["pullback_armed"] = row["open_time"] in armed


def _pullback_view(connection, symbol: str, strategy_id: str, rule: PullbackConfig | None, mark,
                   regime: str) -> dict | None:
    """The pullback entry right now: the line, how long price has been under it, and what would happen next."""
    if rule is None:
        return None
    stored = connection.execute(
        text("SELECT value FROM engine_state WHERE key=:key"), {"key": f"pullback:{symbol}"}
    ).scalar_one_or_none() or {}
    line = Decimal(stored["line"]) if stored.get("line") else None
    below = int(stored.get("below_minutes") or 0)
    uptrend = regime == "bullish" or not rule.requires_uptrend
    last_signal = connection.execute(
        text("""SELECT signal_id, signal_time, status, entry_time, details FROM signals
                WHERE strategy_id=:strategy AND details->>'kind'='pullback'
                ORDER BY signal_time DESC LIMIT 1"""),
        {"strategy": strategy_id},
    ).mappings().one_or_none()
    state = ("warming_up" if line is None else "no_uptrend" if not uptrend
             else "armed" if below >= rule.dwell_minutes else "dipping" if below > 0 else "above")
    return {
        "ema_minutes": rule.ema_minutes, "ema_hours": rule.ema_minutes / 60, "dwell_minutes": rule.dwell_minutes,
        "requires_uptrend": rule.requires_uptrend, "uptrend": uptrend,
        "line": line, "line_at": stored.get("line_at"),
        "below_since": stored.get("below_since"), "below_minutes": below,
        "minutes_to_arm": max(0, rule.dwell_minutes - below) if below else rule.dwell_minutes,
        "distance_to_line_pct": None if (line is None or not mark) else (mark / line - 1) * 100,
        "state": state,
        "last_signal": None if last_signal is None else {
            "signal_id": last_signal["signal_id"], "at": last_signal["signal_time"], "status": last_signal["status"],
            "entry_time": last_signal["entry_time"],
            "below_minutes": (last_signal["details"] or {}).get("below_minutes"),
        },
        "activation_at": stored.get("activation_at"), "checked_at": stored.get("checked_at"),
    }


def _pyramid_view(connection, symbol: str, rule: PyramidConfig | None, allocation: CoinAllocation,
                  positions: list[dict], mark, trend_line) -> dict | None:
    """The pyramid add-on right now: its lots, and what each open lot needs before another is added."""
    if rule is None:
        return None
    counts = dict(connection.execute(
        text("""SELECT parent_position_id, count(*) FROM positions
                WHERE symbol=:s AND parent_position_id IS NOT NULL GROUP BY 1"""),
        {"s": symbol},
    ).all())
    parents = []
    for row in sorted(positions, key=lambda item: item["entry_time"]):
        if row["entry_source"] == "pyramid":
            continue
        adds = int(counts.get(row["position_id"], 0))
        left = rule.maximum_adds - adds
        next_price = (row["entry_fill_price"] * (100 + rule.step_pct * (adds + 1)) / 100) if left > 0 else None
        parents.append({
            "position_id": row["position_id"], "lot_number": row["lot_number"], "source": row["entry_source"],
            "entry_fill_price": row["entry_fill_price"], "adds": adds, "adds_left": left,
            "next_add_price": next_price,
            "distance_to_add_pct": None if (next_price is None or not mark) else (next_price / mark - 1) * 100,
            "above_line": None if (trend_line is None or not mark) else mark > trend_line,
        })
    return {"step_pct": rule.step_pct, "maximum_adds": rule.maximum_adds, "add_exit": rule.add_exit,
            "blocked_entry_hours": list(rule.blocked_entry_hours) if rule.blocked_entry_hours else None,
            "enabled": allocation.enabled("pyramid"), "parents": parents,
            "adds_open": sum(1 for row in positions if row["entry_source"] == "pyramid"),
            "adds_total": sum(counts.values())}


def _trade_stats(connection, symbol: str | None) -> dict:
    stats = dict(connection.execute(
        text(
            """
            SELECT count(*) AS trades,
                   count(*) FILTER (WHERE net_pnl_usd > 0) AS wins,
                   count(*) FILTER (WHERE net_pnl_usd < 0) AS losses,
                   COALESCE(sum(net_pnl_usd) FILTER (WHERE net_pnl_usd > 0), 0) AS gross_win_usd,
                   COALESCE(-sum(net_pnl_usd) FILTER (WHERE net_pnl_usd < 0), 0) AS gross_loss_usd,
                   avg(net_return_pct) FILTER (WHERE net_pnl_usd > 0) AS average_win_pct,
                   avg(net_return_pct) FILTER (WHERE net_pnl_usd < 0) AS average_loss_pct,
                   max(net_return_pct) AS best_pct, min(net_return_pct) AS worst_pct,
                   avg(duration_minutes) AS average_hold_minutes,
                   count(*) FILTER (WHERE exit_reason='trailing_stop') AS trailing_exits,
                   count(*) FILTER (WHERE exit_reason IN ('protective_stop','ambiguous_stop')) AS stop_exits,
                   count(*) FILTER (WHERE exit_reason='manual_close') AS manual_exits,
                   COALESCE(sum(net_pnl_usd) FILTER (WHERE exit_time >= date_trunc('day', now())), 0) AS today_pnl_usd,
                   min(entry_time) AS first_entry,
                   COALESCE(sum(net_pnl_usd), 0) AS realized_usd,
                   COALESCE(sum(entry_fee_usd + exit_fee_usd), 0) AS fees_usd,
                   COALESCE(sum(slippage_usd), 0) AS slippage_usd
            FROM trades WHERE CAST(:symbol AS text) IS NULL OR symbol = :symbol
            """
        ),
        {"symbol": symbol},
    ).mappings().one())
    wins, losses = stats["wins"], stats["losses"]
    return {**stats, "win_rate_pct": wins / (wins + losses) * 100 if wins + losses else None,
            "profit_factor": stats["gross_win_usd"] / stats["gross_loss_usd"] if stats["gross_loss_usd"] else None}


def _coin_view(connection, strategy: dict, usdt_free: Decimal, open_rows: list[dict],
               interval: str, now: datetime, fee_context: FeeContext, with_chart: bool = True) -> dict:
    """Everything one coin page needs: market, entry setup, lots, activity and chart."""
    bucket_sql, bucket_minutes = CHART_INTERVALS[interval]
    breakout_rule = ConsolidationConfig.from_strategy(strategy)
    pullback_rule = PullbackConfig.from_strategy(strategy)
    pyramid_rule = PyramidConfig.from_strategy(strategy)
    config = ExecutionConfig.from_strategy(strategy)
    symbol = strategy["market"]["symbol"]
    strategy_id = strategy["strategy_id"]
    zone = Decimal(str(strategy["entry"]["touch_zone_pct"])) / 100
    market = connection.execute(
        text("SELECT open_time, open, high, low, close FROM candles_1m WHERE symbol=:s ORDER BY open_time DESC LIMIT 1"),
        {"s": symbol},
    ).mappings().one_or_none()
    day_ago = connection.execute(
        text("SELECT close FROM candles_1m WHERE symbol=:s AND open_time <= :t ORDER BY open_time DESC LIMIT 1"),
        {"s": symbol, "t": (market["open_time"] if market else now) - timedelta(hours=24)},
    ).scalar_one_or_none()
    averages = connection.execute(
        text(
            """
            SELECT effective_at, signal_average, average_7d, average_15d, average_30d FROM daily_averages
            WHERE symbol=:s AND effective_at <= :now ORDER BY effective_at DESC LIMIT 1
            """
        ),
        {"s": symbol, "now": now},
    ).mappings().one_or_none()
    signal_state = connection.execute(
        text("SELECT value FROM engine_state WHERE key=:k"), {"k": f"signal_engine:{symbol}"}
    ).scalar_one_or_none() or {}
    signals = [dict(row) for row in connection.execute(
        text(
            """
            SELECT e.episode_id, e.touch_time, e.average_value, e.status AS episode_status, e.details,
                   s.signal_id, s.status, s.reason, s.entry_time
            FROM touch_episodes e LEFT JOIN signals s ON s.episode_id=e.episode_id
            WHERE e.strategy_id=:id ORDER BY e.touch_time DESC LIMIT 25
            """
        ),
        {"id": strategy_id},
    ).mappings().all()]
    signal_counts = dict(connection.execute(
        text(
            """
            SELECT count(*) FILTER (WHERE dip) AS touches,
                   count(*) FILTER (WHERE dip AND status='confirmed') AS confirmed,
                   count(*) FILTER (WHERE dip AND status='skipped_time_window') AS skipped_time_window,
                   count(*) FILTER (WHERE dip AND status='rejected_market_regime') AS rejected_trend,
                   count(*) FILTER (WHERE dip AND status IN ('cancelled_at_episode_exit','expired_wait_limit')) AS not_confirmed,
                   count(*) FILTER (WHERE dip AND status='observed_not_from_below') AS not_from_below,
                   count(*) FILTER (WHERE kind='consolidation') AS breakouts,
                   count(*) FILTER (WHERE kind='consolidation' AND status='confirmed') AS breakouts_confirmed,
                   count(*) FILTER (WHERE kind='pullback') AS pullbacks,
                   count(*) FILTER (WHERE kind='pullback' AND status='confirmed') AS pullbacks_confirmed,
                   count(*) FILTER (WHERE kind='pullback' AND status='skipped_time_window') AS pullbacks_skipped
            FROM (SELECT status, details->>'kind' AS kind, details->>'kind' IS NULL AS dip
                  FROM touch_episodes WHERE strategy_id=:id) episodes
            """
        ),
        {"id": strategy_id},
    ).mappings().one())
    trades = [dict(row) for row in connection.execute(
        text("SELECT * FROM trades WHERE symbol=:s ORDER BY exit_time DESC LIMIT 25"), {"s": symbol}
    ).mappings().all()]
    orders = [dict(row) for row in connection.execute(
        text(
            """
            SELECT o.*, p.symbol FROM orders o JOIN positions p USING (position_id)
            WHERE p.symbol=:s ORDER BY o.requested_at DESC, o.side LIMIT 30
            """
        ),
        {"s": symbol},
    ).mappings().all()]
    # The chart reads up to 160 buckets of candles - most of the table for a 1d chart - so it is only built for
    # the coin page actually on screen, not for all five coins on every refresh.
    chart: list[dict] = []
    if with_chart:
        chart = [dict(row) for row in connection.execute(
            text(
                f"""
                WITH source AS (
                    SELECT * FROM candles_1m WHERE symbol=:s
                      AND open_time >= (SELECT max(open_time) FROM candles_1m WHERE symbol=:s) - make_interval(mins => :lookback)
                ), buckets AS (
                    SELECT date_bin(INTERVAL '{bucket_sql}', open_time, TIMESTAMPTZ '1970-01-01') AS open_time,
                           (array_agg(open ORDER BY open_time))[1] AS open, max(high) AS high, min(low) AS low,
                           (array_agg(close ORDER BY open_time DESC))[1] AS close
                    FROM source GROUP BY 1
                )
                SELECT b.*, a.signal_average FROM buckets b
                LEFT JOIN daily_averages a ON a.symbol=:s AND a.effective_at=date_trunc('day', b.open_time)
                ORDER BY b.open_time
                """
            ),
            {"s": symbol, "lookback": bucket_minutes * 160},
        ).mappings().all()]
        if config.trend_exit_ema_minutes:
            _trend_line(connection, symbol, chart, config.trend_exit_ema_minutes, bucket_minutes)
        if breakout_rule:
            _consolidation_band(connection, symbol, chart, breakout_rule, bucket_minutes)
        if pullback_rule:
            _pullback_overlay(connection, symbol, chart, pullback_rule, bucket_minutes)
    markers: list[dict] = []
    if with_chart:
        markers = [dict(row) for row in connection.execute(
            text(
                """
                SELECT * FROM (
                    SELECT position_id, lot_number, entry_source, parent_position_id, entry_time,
                           entry_fill_price, exit_time,
                           exit_fill_price, exit_reason, realized_pnl_usd, status, trailing_started_at,
                           trend_exit_active,
                           entry_fill_price * (1 + :activation / 100.0) AS trailing_start_price,
                           row_number() OVER (ORDER BY entry_time, position_id) AS trade_number
                    FROM positions WHERE symbol=:s
                ) numbered
                WHERE entry_time >= :start OR exit_time >= :start OR status='open' ORDER BY entry_time
                """
            ),
            {"s": symbol, "start": chart[0]["open_time"] if chart else now, "activation": config.trail_activation_pct},
        ).mappings().all()]
    stats = _trade_stats(connection, symbol)
    # The coin's row only holds its switch and extra-entry toggles now; money and lots belong to the shared pot.
    allocation = read_allocation(connection, symbol) or CoinAllocation.default(strategy)
    pot = read_pot(connection)
    trading_enabled = read_trading_enabled(connection, symbol)
    configured = trading_enabled

    mark = market["close"] if market else None
    average = averages["signal_average"] if averages else None
    lower = average * (1 - zone) if average else None
    upper = average * (1 + zone) if average else None
    regime = "missing"
    if averages and None not in (averages["average_7d"], averages["average_15d"], averages["average_30d"]):
        a7, a15, a30 = averages["average_7d"], averages["average_15d"], averages["average_30d"]
        regime = "bullish" if a7 > a15 > a30 else "bearish" if a7 < a15 < a30 else "neutral"
    blocked = strategy["entry"].get("blocked_entry_hours_utc")
    in_block = bool(blocked and blocked["start"] <= now.hour < blocked["end"])
    if blocked:
        change_hour = blocked["end"] if in_block else blocked["start"]
        window_change = now.replace(hour=change_hour % 24, minute=0, second=0, microsecond=0)
        if window_change <= now:
            window_change += timedelta(days=1)
    else:
        window_change = None
    zone_state = None
    if mark is not None and lower is not None:
        zone_state = "below" if mark < lower else "above" if mark > upper else "inside"
    positions = [row for row in open_rows if row["symbol"] == symbol]
    open_lots = len(positions)
    open_by_source: dict[str, int] = {}
    for row in positions:
        open_by_source[row["entry_source"]] = open_by_source.get(row["entry_source"], 0) + 1
    open_cost = sum((row["allocation_usd"] for row in positions), ZERO)
    # Every coin draws on the pot's lots, so free slots are counted across all coins.
    free_slots = max(0, pot.lots - len(open_rows))
    next_lot_usd = (affordable_lot(pot.lot_size_usd, usdt_free)
                    if trading_enabled and free_slots and pot.lot_size_usd > ZERO else None)

    # Every way in is simply on or off, and they all share the coin's lots, first come first served.
    supported = {"dip": True, "breakout": breakout_rule is not None,
                 "pullback": pullback_rule is not None, "pyramid": pyramid_rule is not None}
    entries = {name: {"supported": supported[name],
                      "enabled": supported[name] and allocation.enabled(name),
                      "open_lots": open_by_source.get("signal" if name == "dip" else name, 0)}
               for name in MODULES}

    # One row per lot the coin owns, in the order they were bought, so the page can draw the pool rather than
    # describe it. Free slots are listed too - an empty slot is what the next signal will fill.
    marks = {symbol: mark}
    for other in {row["symbol"] for row in open_rows} - {symbol}:
        marks[other] = connection.execute(
            text("SELECT close FROM candles_1m WHERE symbol=:s ORDER BY open_time DESC LIMIT 1"), {"s": other}
        ).scalar_one_or_none()

    def slot_of(index: int, row: dict | None) -> dict:
        if row is None:
            return {"number": index, "state": "free", "source": None, "symbol": None, "mine": False}
        armed = bool(row["trailing_active"])
        rides = bool(row["trend_exit_active"]) and config.trend_exit_ema_minutes is not None
        # A slot can belong to another coin in the shared pot, so it is valued at that coin's own price.
        row_mark = marks.get(row["symbol"])
        value = row["quantity"] * row_mark if row_mark else None
        return {"number": index, "state": "open", "source": row["entry_source"], "symbol": row["symbol"],
                "label": coin_label(row["symbol"]), "mine": row["symbol"] == symbol,
                "position_id": row["position_id"], "entry_time": row["entry_time"],
                "entry_fill_price": row["entry_fill_price"], "allocation_usd": row["allocation_usd"],
                "mode": "trend" if rides else "giveback", "armed": armed,
                "trend_exit_pending": bool(row["trend_exit_pending"]),
                "stop_price": row["stop_price"], "parent_position_id": row["parent_position_id"],
                "unrealized_usd": None if value is None else value - row["allocation_usd"],
                "unrealized_pct": None if value is None else (value / row["allocation_usd"] - 1) * 100}

    # The pot's slots as a whole, every coin's lots in the order they were bought; this coin's are marked.
    ordered = sorted(open_rows, key=lambda row: row["entry_time"])
    slots = [slot_of(index + 1, ordered[index] if index < len(ordered) else None)
             for index in range(max(pot.lots, len(ordered)))]
    lot = {"next_lot_usd": next_lot_usd, "lot_number": len(open_rows) + 1,
           "slot_free": free_slots > 0, "free_lots": free_slots, "slots": slots,
           "free_usdt": usdt_free, "shared_open_lots": len(open_rows),
           "shortfall_usd": max(ZERO, pot.lot_size_usd - usdt_free)}
    open_value = sum((row["quantity"] * mark for row in positions), ZERO) if mark else ZERO
    market_age = (now - market["open_time"]).total_seconds() - 60 if market else None
    label = coin_label(symbol)
    return {
        "symbol": symbol, "label": label, "name": COIN_NAMES.get(symbol, label),
        "trading_enabled": trading_enabled, "configured": configured,
        "pending_trading_change": None,
        "strategy": {
            "strategy_id": strategy_id, "name": strategy["name"], "symbol": symbol,
            "signal_timeframe": strategy["market"]["signal_timeframe"],
            "signal_average_days": strategy["averages"]["signal_average_days"],
            "touch_zone_pct": strategy["entry"]["touch_zone_pct"],
            "confirmation_wait_minutes": strategy["entry"]["confirmation"]["maximum_wait_minutes"],
            "blocked_entry_hours_utc": blocked, "stop_pct": config.stop_pct,
            "requires_close_above_30d": (strategy["entry"].get("trend_filter") or {}).get("type")
            == "confirmation_close_above_average_30d",
            "maximum_above_30d_pct": (strategy["entry"].get("trend_filter") or {}).get("maximum_above_average_pct"),
            "trail_activation_pct": config.trail_activation_pct, "trail_giveback_pct": config.trail_giveback_pct,
            "usdt_fee_bps": config.usdt_fee_bps, "bnb_fee_bps": config.bnb_fee_bps, "slippage_bps": config.slippage_bps,
            "backtest": strategy["provenance"]["backtest_bnb_fees"],
            "pullback": None if pullback_rule is None else {
                "ema_minutes": pullback_rule.ema_minutes, "dwell_minutes": pullback_rule.dwell_minutes,
                "requires_uptrend": pullback_rule.requires_uptrend},
            "pyramid": None if pyramid_rule is None else {
                "step_pct": pyramid_rule.step_pct, "maximum_adds": pyramid_rule.maximum_adds,
                "add_exit": pyramid_rule.add_exit},
            "drawdown_review_pct": strategy["evaluation"]["maximum_drawdown_review_pct"],
        },
        "health": {
            "market_age_seconds": round(market_age, 1) if market_age is not None else None,
            "signal_engine": signal_state.get("status", "starting"),
        },
        "market": {
            "price": mark, "open_time": market["open_time"] if market else None,
            "change_24h_pct": (mark / day_ago - 1) * 100 if mark and day_ago else None,
        },
        "setup": {
            "signal_average": average, "zone_lower": lower, "zone_upper": upper, "zone_state": zone_state,
            "distance_to_zone_pct": ((lower / mark - 1) * 100 if zone_state == "below" else
                                     (mark / upper - 1) * 100 if zone_state == "above" else ZERO)
            if zone_state else None,
            "average_7d": averages["average_7d"] if averages else None,
            "average_15d": averages["average_15d"] if averages else None,
            "average_30d": averages["average_30d"] if averages else None,
            "regime": regime, "trend_allows_entries": regime in ("bullish", "neutral"),
            "entry_window_open": not in_block, "entry_window_changes_at": window_change,
            "pending_episode_since": signal_state.get("pending_since"),
            "signal_engine": signal_state.get("status", "starting"),
            "activation_at": signal_state.get("activation_at"),
        },
        "consolidation": _consolidation_view(connection, symbol, strategy["strategy_id"],
                                             breakout_rule, mark),
        "pullback": _pullback_view(connection, symbol, strategy_id, pullback_rule, mark, regime),
        "pyramid": _pyramid_view(connection, symbol, pyramid_rule, allocation, positions, mark,
                                 chart[-1].get("trend_line") if chart else None),
        "entries": entries,
        # What a lot bought right now would do when it wins: ride the trend line, or give profit back.
        "exit_plan": {
            "has_trend_exit": config.trend_exit_ema_minutes is not None,
            "ema_minutes": config.trend_exit_ema_minutes,
            "requires_uptrend": config.trend_exit_requires_uptrend,
            "next_lot_mode": ("trend" if config.trend_exit_ema_minutes is not None
                              and (regime == "bullish" or not config.trend_exit_requires_uptrend)
                              else "giveback"),
            "trend_line": chart[-1].get("trend_line") if chart else None,
            "giveback_pct": config.trail_giveback_pct,
            "activation_pct": config.trail_activation_pct,
            "stop_pct": config.stop_pct,
        },
        "lots": {**lot, "open_lots": open_lots, "max_lots": pot.lots,
                 "lot_size_usd": pot.lot_size_usd, "target_capital_usd": pot.total_usd},
        "money": {
            "symbol": symbol, "name": COIN_NAMES.get(symbol, label), "label": label,
            "trading_enabled": trading_enabled, "configured": configured,
            "lot_size_usd": pot.lot_size_usd, "lots": pot.lots,
            "entries": {name: {"enabled": allocation.enabled(name) and supported[name],
                               "supported": supported[name]} for name in MODULES},
            "target_capital_usd": pot.total_usd,
            "open_lots": open_lots, "open_cost_usd": open_cost, "open_value_usd": open_value,
            "capital_usd": open_cost, "value_usd": open_value,
            "realized_pnl_usd": stats["realized_usd"], "unrealized_pnl_usd": open_value - open_cost,
        },
        "stats": stats,
        "signal_counts": signal_counts,
        "positions": [_position_view(row, config, mark, fee_context, now) for row in positions],
        "signals": signals, "trades": trades, "orders": orders,
        "chart": chart, "markers": markers,
    }
