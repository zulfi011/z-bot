import type { EntrySource } from "./api";

/**
 * The plain names used everywhere: chart badges, lot cards, trade lists, coin pages. One place, so a name is never
 * spelled two ways. The letter is the name's first letter; the colours live in CSS.
 */
export const SOURCE: Record<EntrySource, { letter: string; name: string; cls: string; long: string; tip: string }> = {
  signal: { letter: "D", name: "Dip", cls: "src-dip", long: "the dip into the average",
    tip: "Dip: buys when the price dips into the coin's average while the trend allows it." },
  breakout: { letter: "Q", name: "Quiet-band breakout", cls: "src-breakout", long: "a breakout from a quiet band",
    tip: "Quiet-band breakout: buys when the price breaks above a quiet, narrow range it has been stuck in." },
  pullback: { letter: "P", name: "Pullback", cls: "src-pullback", long: "a pullback in an uptrend",
    tip: "Pullback: in a clean uptrend, buys a short dip below the trend line once the price turns back up." },
  pyramid: { letter: "+", name: "Add-on", cls: "src-pyramid", long: "an add-on to a lot that was already winning",
    tip: "Add-on: adds one more lot to a lot that is already winning, while the climb holds." },
  manual: { letter: "B", name: "Buy now", cls: "src-manual", long: "you (Buy now)",
    tip: "Buy now: you bought this lot yourself with the Buy now button." },
};

export const sourceOf = (value: string | null | undefined) => SOURCE[(value ?? "signal") as EntrySource] ?? SOURCE.signal;

/** How a lot is sold once it is in profit. */
export const EXIT = {
  trend: { name: "Trend ride", cls: "rides",
    tip: "Trend ride: in an uptrend the lot is held while the price stays above the trend line, and sold when a minute closes below it." },
  giveback: { name: "Trailing stop", cls: "trails",
    tip: "Trailing stop: after a set gain, a stop follows the price up and sells if it gives back a set share of the best profit." },
} as const;

export const exitOf = (mode: string | null | undefined) => (mode === "trend" ? EXIT.trend : EXIT.giveback);
