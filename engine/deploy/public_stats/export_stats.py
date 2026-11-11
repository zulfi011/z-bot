#!/usr/bin/env python3
"""Z-Bot public live stats: percentages only.

Reads the bot's database through the read-only `zbot_stats` role (create_readonly_role.sql) and writes one JSON
file for the public stats page. It never writes to the database and never touches the running bot.

Only live trades count: a lot is live when Binance returned an order id for its buy (shadow lots have none).
Dollar amounts never leave the database: each trade's effect on the account is computed inside the query as
profit / wallet value when the lot was bought, and only that percentage is exported.

Usage (on the server):  python3 export_stats.py --compose-dir /opt/z-bot/engine --out /path/to/docs/stats.json
Testing elsewhere:      python3 export_stats.py --psql "docker exec -i some-postgres psql -U zbot_stats -d papertrading" --out x.json
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

SQL = r"""
WITH live_trades AS (
    SELECT t.trade_id, t.symbol, t.entry_source, t.exit_reason, t.exit_mode, t.entry_time, t.exit_time,
           t.duration_minutes, t.net_return_pct, t.net_pnl_usd,
           p.entry_order_id, COALESCE(p.exit_order_id, p.stop_order_id) AS exit_order_id
    FROM paper_trades t
    JOIN paper_positions p ON p.position_id = t.position_id
    WHERE p.entry_order_id IS NOT NULL
), weighted AS (
    SELECT lt.*,
           (SELECT s.wallet_value_usd FROM account_snapshots s
             WHERE s.timestamp <= lt.entry_time ORDER BY s.timestamp DESC LIMIT 1) AS wallet
    FROM live_trades lt
)
SELECT json_build_object(
    'generated_at', now(),
    'live_since', (SELECT min(timestamp) FROM account_snapshots WHERE trading_mode = 'live'),
    'trades', COALESCE((
        SELECT json_agg(json_build_object(
            'symbol', symbol, 'entry', entry_source, 'exit', exit_reason, 'exit_style', exit_mode,
            'opened', entry_time, 'closed', exit_time, 'minutes', duration_minutes,
            'return_pct', round(net_return_pct::numeric, 3),
            'account_pct', CASE WHEN wallet > 0 THEN round((net_pnl_usd / wallet * 100)::numeric, 4) END,
            'entry_order', entry_order_id, 'exit_order', exit_order_id
        ) ORDER BY exit_time) FROM weighted), '[]'::json),
    'open', COALESCE((
        SELECT json_agg(json_build_object(
            'symbol', p.symbol, 'entry', p.entry_source, 'opened', p.entry_time,
            'unrealized_pct', CASE WHEN p.entry_fill_price > 0
                THEN round(((c.close / p.entry_fill_price - 1) * 100)::numeric, 3) END,
            'entry_order', p.entry_order_id
        ) ORDER BY p.entry_time)
        FROM paper_positions p
        LEFT JOIN LATERAL (SELECT close FROM candles_1m WHERE symbol = p.symbol
                           ORDER BY open_time DESC LIMIT 1) c ON true
        WHERE p.status = 'open' AND p.entry_order_id IS NOT NULL), '[]'::json)
);
"""

# Every key that may appear in the published file. Anything else stops the export.
ALLOWED_KEYS = {
    "generated_at", "live_since", "days_live", "trades", "open", "summary", "curve", "monthly", "coins",
    "symbol", "entry", "exit", "exit_style", "opened", "closed", "minutes", "return_pct", "account_pct",
    "entry_order", "exit_order", "unrealized_pct", "t", "pct", "month", "wins", "losses", "win_rate_pct",
    "avg_win_pct", "avg_loss_pct", "profit_factor", "total_return_pct", "max_drawdown_pct", "best_pct",
    "worst_pct", "avg_hold_hours", "open_lots", "avg_return_pct", "return_contribution_pct", "note",
}
FORBIDDEN_FRAGMENTS = ("usd", "quantity", "wallet", "balance", "allocation", "cash", "pot", "lot_size")


def compose_db_name(compose_dir: Path) -> str:
    """Reads only POSTGRES_DB from the server's .env; nothing else in that file is looked at."""
    env = compose_dir / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("POSTGRES_DB="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or "papertrading"
    return "papertrading"


def run_query(args) -> dict:
    if args.psql:
        command, cwd = shlex.split(args.psql), None
    else:
        compose_dir = Path(args.compose_dir)
        command = ["docker", "compose", "exec", "-T", "db", "psql", "-U", "zbot_stats", "-d",
                   compose_db_name(compose_dir)]
        cwd = compose_dir
    command += ["-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-f", "-"]
    result = subprocess.run(command, input=SQL, cwd=cwd, capture_output=True, text=True, timeout=90)
    if result.returncode != 0:
        sys.exit(f"query failed: {result.stderr.strip()}")
    return json.loads(result.stdout.strip())


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def r(value, digits=2):
    return None if value is None else round(value, digits)


def summarize(trades: list[dict]) -> dict:
    returns = [t["return_pct"] for t in trades if t["return_pct"] is not None]
    wins = [x for x in returns if x > 0]
    losses = [x for x in returns if x < 0]
    effects = [t["account_pct"] for t in trades if t["account_pct"] is not None]
    gained = sum(x for x in effects if x > 0)
    lost = -sum(x for x in effects if x < 0)
    growth = 1.0
    for x in effects:
        growth *= 1 + x / 100
    hours = [t["minutes"] / 60 for t in trades if t["minutes"] is not None]
    return {
        "trades": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate_pct": r(len(wins) / len(returns) * 100, 1) if returns else None,
        "avg_win_pct": r(sum(wins) / len(wins)) if wins else None,
        "avg_loss_pct": r(sum(losses) / len(losses)) if losses else None,
        "profit_factor": r(gained / lost) if lost else None,
        "total_return_pct": r((growth - 1) * 100) if effects else None,
        "best_pct": r(max(returns)) if returns else None,
        "worst_pct": r(min(returns)) if returns else None,
        "avg_hold_hours": r(sum(hours) / len(hours), 1) if hours else None,
    }


def build(raw: dict) -> dict:
    trades = raw["trades"]
    for t in trades:
        t["return_pct"] = None if t["return_pct"] is None else float(t["return_pct"])
        t["account_pct"] = None if t["account_pct"] is None else float(t["account_pct"])
    for lot in raw["open"]:
        lot["unrealized_pct"] = None if lot["unrealized_pct"] is None else float(lot["unrealized_pct"])

    # Account curve from closed trades: each trade's effect compounds on the last.
    live_since = raw["live_since"] or (trades[0]["opened"] if trades else None)
    curve, growth, peak, worst_dd = [], 1.0, 1.0, 0.0
    if live_since:
        curve.append({"t": live_since, "pct": 0.0})
    for t in trades:
        if t["account_pct"] is None:
            continue
        growth *= 1 + t["account_pct"] / 100
        peak = max(peak, growth)
        worst_dd = min(worst_dd, (growth / peak - 1) * 100)
        curve.append({"t": t["closed"], "pct": r((growth - 1) * 100, 3)})

    monthly: "OrderedDict[str, list]" = OrderedDict()
    for t in trades:
        monthly.setdefault(t["closed"][:7], []).append(t)
    months = [{"month": month, **{k: v for k, v in summarize(rows).items()
                                  if k in ("trades", "win_rate_pct", "total_return_pct")}}
              for month, rows in monthly.items()]

    coins = []
    for symbol in sorted({t["symbol"] for t in trades} | {lot["symbol"] for lot in raw["open"]}):
        rows = [t for t in trades if t["symbol"] == symbol]
        s = summarize(rows)
        returns = [t["return_pct"] for t in rows if t["return_pct"] is not None]
        coins.append({"symbol": symbol, "trades": s["trades"], "win_rate_pct": s["win_rate_pct"],
                      "avg_return_pct": r(sum(returns) / len(returns)) if returns else None,
                      "return_contribution_pct": s["total_return_pct"],
                      "open_lots": len([lot for lot in raw["open"] if lot["symbol"] == symbol])})
    coins.sort(key=lambda c: (c["return_contribution_pct"] or 0), reverse=True)

    now = parse_time(raw["generated_at"])
    summary = {**summarize(trades), "max_drawdown_pct": r(worst_dd), "open_lots": len(raw["open"])}
    return {
        "generated_at": raw["generated_at"],
        "live_since": live_since,
        "days_live": (now - parse_time(live_since)).days if live_since else 0,
        "summary": summary, "curve": curve, "monthly": months, "coins": coins,
        "open": raw["open"], "trades": trades,
        "note": "Live Binance spot trades only, after fees. Percentages only. Not financial advice.",
    }


def check_keys(value, path="$"):
    if isinstance(value, dict):
        for key, inner in value.items():
            if key not in ALLOWED_KEYS or any(f in key.lower() for f in FORBIDDEN_FRAGMENTS):
                sys.exit(f"refusing to publish unexpected field {path}.{key}")
            check_keys(inner, f"{path}.{key}")
    elif isinstance(value, list):
        for item in value:
            check_keys(item, path + "[]")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--compose-dir", default="/opt/z-bot/engine")
    parser.add_argument("--psql", help="psql command to use instead of docker compose (for testing)")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    stats = build(run_query(args))
    check_keys(stats)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(stats, indent=1) + "\n")
    tmp.replace(out)
    print(f"wrote {out}: {stats['summary']['trades']} trades, {stats['summary']['open_lots']} open lots")


if __name__ == "__main__":
    main()
