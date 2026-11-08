import type { EntrySource } from "./api";

/** Who opened a lot, the same way everywhere: chart badges, lot cards, trade lists. The colours live in CSS. */
export const SOURCE: Record<EntrySource, { letter: string; name: string; cls: string; long: string }> = {
  signal: { letter: "D", name: "Dip", cls: "src-dip", long: "the dip into the average" },
  breakout: { letter: "C", name: "Mode C", cls: "src-breakout", long: "a Mode C break out of a quiet band" },
  pullback: { letter: "P", name: "Pullback", cls: "src-pullback", long: "the pullback entry" },
  pyramid: { letter: "+", name: "Add", cls: "src-pyramid", long: "a pyramid add to a lot that was already winning" },
  manual: { letter: "M", name: "You", cls: "src-manual", long: "you (Buy now)" },
};

export const sourceOf = (value: string | null | undefined) => SOURCE[(value ?? "signal") as EntrySource] ?? SOURCE.signal;
