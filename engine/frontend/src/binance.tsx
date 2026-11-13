import { useEffect, useState, type ReactNode } from "react";
import { attachBinance, detachBinance, reachability, type BinanceCredentials, type Reachability } from "./api";

const LIVE_RESULTS = "https://zulfi011.github.io/z-bot/";
const CHART_ICON = <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M2 13.5h12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /><path d="M2.5 10.5l3.5-3.5 2.5 2.5 5-5.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;

/** Top-bar button to the public page with Z-Bot's own live track record. A label, not a bare icon, so it reads at once. */
export function LiveResultsLink() {
  return <a className="live-results" href={`${LIVE_RESULTS}#results`} target="_blank" rel="noreferrer"
    title="Every trade of a simulated account at Binance prices, after fees, updated daily" aria-label="Results (opens in a new tab)">
    {CHART_ICON}<span className="long">Results</span><span className="short">Results</span><span className="arrow" aria-hidden="true">↗</span>
  </a>;
}

/** A page of the online guide, e.g. guideUrl("strategies", "dip"). */
export const guideUrl = (page: string, anchor?: string) => `${LIVE_RESULTS}guide.html?p=${page}${anchor ? `#${anchor}` : ""}`;

/** Small "Learn more" link to the online guide, for the foot of a card. */
export function LearnMore({ page, anchor, children = "Learn more" }: { page: string; anchor?: string; children?: ReactNode }) {
  return <a className="learn-more" href={guideUrl(page, anchor)} target="_blank" rel="noreferrer">{children} →</a>;
}

const API_MANAGEMENT = "https://www.binance.com/en/my/settings/api-management";
const KEY_PATTERN = /^[A-Za-z0-9]{16,128}$/;

const KEY_ICON = <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><circle cx="5" cy="8" r="3" fill="none" stroke="currentColor" strokeWidth="1.6" /><path d="M8 8h6.5M12 8v2.5M14.5 8v2" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>;

/** Top-bar button: yellow until a Binance account is attached, then a quiet "Binance" chip. */
export function AttachBinanceButton({ credentials, onOpen }: { credentials: BinanceCredentials | null; onOpen: () => void }) {
  if (!credentials) return null;
  if (credentials.attached) {
    return <button className="binance-chip" onClick={onOpen} title={`Binance account attached (key ${credentials.key_hint})`}>
      <i aria-hidden />Binance</button>;
  }
  return <button className="binance-attach" onClick={onOpen}>
    {KEY_ICON}<span className="long">Attach Binance account</span><span className="short">Attach Binance</span></button>;
}

type Where = "computer" | "cloud";

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return <li className="step"><span className="step-n">{n}</span><div><b>{title}</b><div className="step-body">{children}</div></div></li>;
}

function CopyIp({ ip }: { ip: string | undefined }) {
  const [copied, setCopied] = useState(false);
  if (!ip) return <code>checking…</code>;
  return <button type="button" className="ip-copy" onClick={async () => {
    try { await navigator.clipboard.writeText(ip); setCopied(true); window.setTimeout(() => setCopied(false), 1500); } catch { /* ignore */ }
  }} title="Copy">{ip}<small>{copied ? "copied" : "copy"}</small></button>;
}

function ReachLine({ reach }: { reach: Reachability | null }) {
  if (!reach) return <p className="reach muted">Checking whether this machine can reach Binance's trading API…</p>;
  const ok = reach.state === "reachable";
  return <p className={`reach ${ok ? "ok" : "bad"}`}>
    <i aria-hidden />{ok ? "This machine can reach Binance's trading API."
      : reach.state === "blocked" ? "Binance refuses API trading from this machine's region (451). Run Z-Bot on a server in a supported region."
        : `Binance's trading API could not be checked: ${reach.message}`}</p>;
}

function AttachForm({ where, reach, onAttached, onCancel }:
  { where: Where; reach: Reachability | null; onAttached: (next: BinanceCredentials) => void; onCancel: () => void }) {
  const [key, setKey] = useState("");
  const [secret, setSecret] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = KEY_PATTERN.test(key.trim()) && KEY_PATTERN.test(secret.trim());
  const ip = reach?.public_ip;
  return <form onSubmit={async event => {
    event.preventDefault();
    if (!ready || busy) return;
    setBusy(true); setError(null);
    try { onAttached(await attachBinance(key.trim(), secret.trim())); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Binance did not accept the key"); }
    finally { setBusy(false); }
  }}>
    <ol className="steps">
      <Step n={1} title="Create an API key on Binance">
        Open <a href={API_MANAGEMENT} target="_blank" rel="noreferrer">API Management</a> (Profile → API Management),
        choose <b>Create API</b> → <b>System generated</b>, give the key a name and finish the security check.
      </Step>
      <Step n={2} title="Give it trading rights only">
        Tick <b>Enable Reading</b> and <b>Enable Spot &amp; Margin Trading</b>. Leave <b>Enable Withdrawals</b> off:
        Z-Bot never needs it and refuses keys that can withdraw.
      </Step>
      {where === "computer"
        ? <Step n={3} title="Lock the key to your internet connection">
          Recommended: choose <b>Restrict access to trusted IPs only</b> and add this connection's public IP <CopyIp ip={ip} />.
          If your home IP changes, Binance will refuse the key until you update it there.
        </Step>
        : <Step n={3} title="Meet Binance's rules for a cloud server">
          <ul className="bullets">
            <li>The server needs a <b>fixed (static) IPv4 address</b>. Choose <b>Restrict access to trusted IPs only</b> and add it: <CopyIp ip={ip} /></li>
            <li>Pick a region where Binance.com allows API trading (for example Frankfurt). The US, UK, Japan and Singapore are refused.</li>
            <li>Keep the dashboard private: set a control key (<code>STRATEGY_EDIT_TOKEN</code>) and reach it over SSH or a VPN, never an open port.</li>
          </ul>
        </Step>}
      <Step n={4} title="Paste both keys here">
        Binance shows the <b>Secret Key</b> only once, so copy it straight away.
      </Step>
    </ol>
    <ReachLine reach={reach} />
    <label className="field"><span>API Key</span>
      <input value={key} onChange={event => setKey(event.target.value)} autoComplete="off" spellCheck={false}
        autoCapitalize="off" placeholder="64 letters and numbers" /></label>
    <label className="field"><span>Secret Key</span>
      <div className="secret-input">
        <input type={show ? "text" : "password"} value={secret} onChange={event => setSecret(event.target.value)}
          autoComplete="new-password" spellCheck={false} autoCapitalize="off" placeholder="Shown once by Binance" />
        <button type="button" className="ghost small-button" onClick={() => setShow(!show)}>{show ? "Hide" : "Show"}</button>
      </div></label>
    <p className="sheet-note">Z-Bot checks the key with Binance, then keeps it only on this machine: never in the
      database, never sent anywhere except Binance. Trading stays in <b>Shadow</b> until you press <b>Go live</b>.</p>
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="sheet-actions">
      <button type="button" className="ghost" onClick={onCancel} disabled={busy}>Cancel</button>
      <button type="submit" className="binance-submit" disabled={!ready || busy}>{busy ? "Checking with Binance…" : "Attach account"}</button>
    </div>
  </form>;
}

/** The popup behind the yellow button: how to make a key, then attach it; or the attached key and how to remove it. */
export function BinanceSheet({ credentials, live, onChanged, onCancel }:
  { credentials: BinanceCredentials | null; live: boolean; onChanged: (next: BinanceCredentials, message: string) => void; onCancel: () => void }) {
  const [where, setWhere] = useState<Where>("computer");
  const [reach, setReach] = useState<Reachability | null>(null);
  const [replacing, setReplacing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { reachability().then(setReach).catch(() => setReach(null)); }, []);

  if (credentials?.attached && !replacing) {
    const fromEnv = credentials.source === "environment";
    return <div>
      <p className="attached-line"><i aria-hidden /><span>Attached · key <code>{credentials.key_hint}</code></span></p>
      <p className="sheet-text">{fromEnv
        ? <>This key is set in the server's environment (<code>BINANCE_API_KEY</code>). Change or remove it there, or replace it here.</>
        : <>The key was attached from this dashboard and is kept only on this machine.</>}
        {" "}{live ? "Trading is live: real orders go to this account." : "Trading is in shadow mode until you press Go live."}</p>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="sheet-actions">
        <button type="button" className="ghost" onClick={() => setReplacing(true)} disabled={busy}>Replace key</button>
        {!fromEnv && <button type="button" className="danger" disabled={busy || live}
          title={live ? "Switch to Shadow first" : undefined}
          onClick={async () => {
            setBusy(true); setError(null);
            try { onChanged(await detachBinance(), "Binance key removed from this machine."); }
            catch (reason) { setError(reason instanceof Error ? reason.message : "Could not remove the key"); }
            finally { setBusy(false); }
          }}>{busy ? "Removing…" : "Remove key"}</button>}
      </div>
      {live && !fromEnv && <p className="small muted">Switch to Shadow before removing the key.</p>}
    </div>;
  }

  return <div>
    <p className="sheet-text">Z-Bot trades your own Binance spot account through an API key. Your money stays on
      Binance, and the key can trade but never withdraw.</p>
    <div className="segmented" role="tablist" aria-label="Where Z-Bot runs">
      <button type="button" role="tab" aria-selected={where === "computer"} className={where === "computer" ? "active" : ""}
        onClick={() => setWhere("computer")}>On my computer</button>
      <button type="button" role="tab" aria-selected={where === "cloud"} className={where === "cloud" ? "active" : ""}
        onClick={() => setWhere("cloud")}>On a cloud server</button>
    </div>
    <AttachForm where={where} reach={reach} onCancel={replacing ? () => setReplacing(false) : onCancel}
      onAttached={next => onChanged(next, "Binance account attached. Trading stays in Shadow until you press Go live.")} />
  </div>;
}
