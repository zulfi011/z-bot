import { useCallback, useEffect, useRef, useState } from "react";
import { COIN_ORDER, coinLabel, getJson, type Dashboard, type Interval } from "./api";
import { ControlsProvider, useControls, DeviceLockButton } from "./controls";
import { ago, pct, tone } from "./format";
import { MainPage } from "./MainPage";
import { CoinPage } from "./CoinPage";
import { AlertBanner } from "./panels";
import { CoinToken } from "./ui";

/** "main" or a coin symbol such as "SOLUSDT". */
type Page = string;

const pageFromHash = (): Page => {
  const coin = COIN_ORDER.find(symbol => `#${coinLabel(symbol).toLowerCase()}` === location.hash.toLowerCase());
  return coin ?? "main";
};
type Theme = "dark" | "light";

const stored = <T extends string>(key: string, fallback: T, allowed: T[]): T => {
  try { const value = localStorage.getItem(key) as T | null; return value && allowed.includes(value) ? value : fallback; }
  catch { return fallback; }
};
const store = (key: string, value: string) => { try { localStorage.setItem(key, value); } catch { /* ignore */ } };

function Flash() {
  const { flash, dismissFlash } = useControls();
  return flash ? <div className="flash" role="status"><span>{flash}</span>
    <button className="banner-close" aria-label="Hide message" onClick={dismissFlash}>✕</button></div> : null;
}

/** Main plus one chip per coin, in a row that scrolls sideways - it holds any number of coins on any screen. */
function PageRail({ page, coins, data, onSelect }:
  { page: Page; coins: string[]; data: Dashboard | null; onSelect: (page: Page) => void }) {
  const rail = useRef<HTMLElement>(null);
  // Keep the open page's chip in view (e.g. after opening a coin from the leaderboard). Only the rail scrolls,
  // sideways; scrollIntoView would also move the page.
  const first = useRef(true);
  useEffect(() => {
    const element = rail.current;
    const chip = element?.querySelector<HTMLElement>(".rail-chip.active");
    if (!element || !chip) return;
    const left = chip.offsetLeft - (element.clientWidth - chip.offsetWidth) / 2;
    element.scrollTo({ left: Math.max(0, left), behavior: first.current ? "auto" : "smooth" });
    first.current = false;
  }, [page, coins.length, data != null]);  // chips widen once prices arrive, so centre again then
  return <nav className="page-rail" aria-label="Pages" ref={rail}>
    <button className={`rail-chip ${page === "main" ? "active" : ""}`} aria-current={page === "main" ? "page" : undefined}
      onClick={() => onSelect("main")}><span className="rail-home" aria-hidden>⌂</span>Main</button>
    {coins.map(symbol => {
      const coin = data?.coins[symbol];
      const change = coin?.market.change_24h_pct;
      return <button key={symbol} className={`rail-chip ${page === symbol ? "active" : ""}`}
        aria-current={page === symbol ? "page" : undefined} onClick={() => onSelect(symbol)}>
        <CoinToken symbol={symbol} />{coinLabel(symbol)}
        {change != null && <small className={tone(change)}>{pct(change, 1)}</small>}
        {coin && coin.positions.length > 0 && <i className="rail-dot" title={`${coin.positions.length} open lot${coin.positions.length === 1 ? "" : "s"}`} />}
      </button>;
    })}
  </nav>;
}

export default function App() {
  const [page, setPage] = useState<Page>(pageFromHash);
  const [theme, setTheme] = useState<Theme>(() => stored("sol-desk-theme", "dark", ["dark", "light"]));
  const [interval, setInterval] = useState<Interval>(() => stored("sol-desk-interval", "15m", ["3m", "15m", "1h", "4h", "1d"]));
  const [chartMode, setChartMode] = useState<"line" | "candles">(() => stored("sol-desk-chart", "candles", ["line", "candles"]));
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    // Only the coin page on screen needs its price chart; the main page asks for none.
    const chart = page === "main" ? "" : `&chart=${page}`;
    try { setData(await getJson<Dashboard>(`/api/v1/dashboard?interval=${interval}${chart}`)); setError(null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Dashboard unavailable"); }
    finally { setLoading(false); }
  }, [interval, page]);

  useEffect(() => {
    load();
    const timer = window.setInterval(() => document.visibilityState === "visible" && load(), 15_000);
    const onVisible = () => document.visibilityState === "visible" && load();
    document.addEventListener("visibilitychange", onVisible);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", onVisible); };
  }, [load]);
  useEffect(() => { document.documentElement.dataset.theme = theme; store("sol-desk-theme", theme); }, [theme]);
  useEffect(() => {
    // Follow the address bar (#sol, #eth) when the user goes back or edits it.
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => store("sol-desk-interval", interval), [interval]);
  useEffect(() => store("sol-desk-chart", chartMode), [chartMode]);
  useEffect(() => {
    history.replaceState(null, "", page === "main" ? "#" : `#${coinLabel(page).toLowerCase()}`);
    window.scrollTo({ top: 0 });
  }, [page]);

  const live = data && !error && (data.health.market_age_seconds ?? 999) < 180;
  const coins = data?.coin_order ?? COIN_ORDER;
  return <ControlsProvider data={data} refresh={load}>
    <div className="app">
      <header className="topbar">
        <div className="brand"><div>
          <strong className="wordmark" aria-label="Z-Bot"><img className="logo-z on-dark" src="/zbot-z-dark.svg" alt="" /><img className="logo-z on-light" src="/zbot-z-light.svg" alt="" />-Bot</strong>
          <small>{coins.length} coins</small></div></div>
        <div className="top-actions">
          <span className={`live ${live ? "on" : "off"}`} title={data ? `Updated ${ago(data.generated_at)}` : "Connecting"}>
            <i />{live ? "Live" : error ? "Offline" : "Waiting"}</span>
          <DeviceLockButton />
          <button className="icon-button" aria-label="Refresh" onClick={load} disabled={loading}><span className={loading ? "spin" : ""}>↻</span></button>
          <button className="icon-button" aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? "☀" : "☾"}</button>
        </div>
      </header>
      <PageRail page={page} coins={coins} data={data} onSelect={setPage} />

      <main>
        {error && <div className="banners"><div className="banner critical"><p><b>Can't reach the server.</b> {error}. Retrying automatically.</p></div></div>}
        {data && <AlertBanner data={data} />}
        <Flash />
        {!data ? <div className="loading">{error ? "Waiting for the server…" : "Loading your account…"}</div>
          : page !== "main" && data.coins[page] ? <CoinPage key={page} data={data} coin={data.coins[page]} interval={interval} onInterval={setInterval} chartMode={chartMode} onChartMode={setChartMode} />
            : <MainPage data={data} onOpenCoin={setPage} />}
        <footer>All times UTC · {data?.trading.mode === "live" ? "Live — the bot places real orders on your Binance account."
          : data?.trading.mode === "off" ? "Stopped — no new lots are opened."
            : "Shadow — orders are worked out and recorded, but nothing is sent to Binance."}</footer>
      </main>

    </div>
  </ControlsProvider>;
}
