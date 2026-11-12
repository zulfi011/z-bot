"""Per-coin contribution inside the shared pot for the chosen plans vs live."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import compounding_full_analysis as ca
from compounding_full_analysis import Policy, replay

markets, cands = ca.load()
signals = pd.Series([c.coin for c in cands if ca.START <= c.entry_time < ca.END]).value_counts()
rows = []
plans = [Policy("LIVE", "live", 300.0), Policy("N5 +$20", "step", 300.0, 5, 20.0),
         Policy("N5 +$30", "step", 300.0, 5, 30.0)]
for p in plans:
    s, led, eq = replay(markets, cands, p, want_frames=True)
    g = led.groupby("coin").agg(trades=("pnl", "size"), profit=("pnl", "sum"), win_pct=("pnl", lambda x: 100 * (x > 0).mean()),
                                losses_usd=("pnl", lambda x: x[x <= 0].sum()), avg_buy=("spend", "mean"))
    g["signals"] = signals
    g["taken_pct"] = 100 * g.trades / g.signals
    g["share_of_profit_pct"] = 100 * g.profit / g.profit.sum()
    g.insert(0, "plan", p.name)
    rows.append(g.reset_index())
    led.to_csv(ca.OUT / "ideal_n_step" / f"ledger_{p.name.replace(' ', '').replace('$', '').replace('+', '_')}.csv", index=False)
out = pd.concat(rows)
pd.set_option("display.width", 220)
print(out.round(2).to_string(index=False))
out.to_csv(ca.OUT / "ideal_n_step" / "per_coin.csv", index=False)
