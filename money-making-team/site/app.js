/* Local Money Team desk. One live payload drives Desk + Learn. */
const POLL_MS = 5000;
const $ = (id) => document.getElementById(id);
const money = (n) => (n < 0 ? "-" : "") + "$" + Math.abs(n).toFixed(2);
const signed = (n) => (n > 0 ? "+" : n < 0 ? "-" : "") + "$" + Math.abs(n).toFixed(2);
const cents = (n) => Number(n).toFixed(1) + "¢";
const NS = "http://www.w3.org/2000/svg";

let state = null;
let tab = location.hash === "#learn" ? "learn" : "desk";

function isOnchainRow(c) {
  if (!c) return false;
  if (c.id === "onchain") return true;
  return /on-?chain/i.test(String(c.venue || ""));
}

function cashRows() {
  return state.cash || [];
}

function cashOf(name) {
  return cashRows().find((c) => (c.venue || "").toLowerCase().includes(name)) || { spendable: 0, inPlay: 0 };
}

function feedFor(name) {
  const needle = name.toLowerCase();
  return (state.feeds || []).find((f) => (f.name || "").toLowerCase().includes(needle)) || null;
}

function polyline(vals, w, h, pad) {
  if (!vals.length) return [];
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  return vals.map((v, i) => {
    const x = pad + (vals.length === 1 ? 0 : i / (vals.length - 1)) * (w - pad * 2);
    const y = pad + (1 - (v - min) / span) * (h - pad * 2);
    return [x, y];
  });
}

function sparkSvg(vals, ref, w, h, color) {
  if (!vals || vals.length < 1) return "";
  const pad = 4;
  const pts = polyline(vals, w, h, pad);
  const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  const refY = pad + (1 - (ref - min) / span) * (h - pad * 2);
  const last = pts[pts.length - 1];
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img">
    <line x1="0" y1="${refY.toFixed(1)}" x2="${w}" y2="${refY.toFixed(1)}"
          stroke="var(--rule)" stroke-width="1" stroke-dasharray="3 3"/>
    <path d="${d}" fill="none" stroke="${color}" stroke-width="1.75"
          stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="3" fill="${color}"/>
  </svg>`;
}

function heroSource() {
  if (state.open) return { row: state.open, live: true };
  const row = (state.blotter || [])[0];
  if (!row) return null;
  return { row: row.hero || row, live: false };
}

function renderHero() {
  const src = heroSource();
  const el = $("hero");
  if (!src) {
    el.innerHTML = '<div class="empty">No tickets yet. The desk is flat.</div>';
    return;
  }
  const o = src.row;
  const game = o.away && o.home && o.away.abbr && o.home.abbr;
  const result = o.result || o.period || (src.live ? "OPEN" : "");
  const resCls = result === "WON" ? "won" : result === "LOST" ? "lost" : "open";
  const drift = (o.mark ?? o.entry) - o.entry;
  const pl = o.pl;
  const un =
    src.live && o.entry
      ? (o.size / (o.entry / 100)) * (((o.mark ?? o.entry) - o.entry) / 100)
      : pl;
  const marks = o.marks && o.marks.length ? o.marks : [o.entry, o.mark ?? o.entry];
  const left = game
    ? `<div class="score">
        <div class="team ${o.away.runs > o.home.runs ? "lead" : ""}">
          <div class="team-abbr">${o.away.abbr}</div>
          <div class="team-runs">${o.away.runs ?? 0}</div>
        </div>
        <div class="dash">–</div>
        <div class="team ${o.home.runs >= o.away.runs ? "lead" : ""}">
          <div class="team-abbr">${o.home.abbr}</div>
          <div class="team-runs">${o.home.runs ?? 0}</div>
        </div>
        <div class="inning">${o.period || result}</div>
      </div>
      <div class="mktname">${o.market} · ${o.venue} · ticket ${o.ticket || o.marketId || ""}</div>`
    : `<div class="board-tag">${src.live ? "Open ticket" : "Latest ticket"}</div>
      <div class="score">
        <div class="crypto-name">${o.market || "—"}</div>
        <div class="period ${resCls}">${result || "—"}</div>
      </div>
      <div class="mktname">${o.venue || ""} · ${o.ticket || o.marketId || ""}</div>`;

  el.innerHTML = `
    <div class="board-l">
      ${left}
      <div class="ticketline">
        <span class="side">${o.side || "—"}</span>
        filled at <b>${cents(o.entry)}</b>, ${money(o.size)} ${src.live ? "at risk" : "size"}
      </div>
      <div class="markrow">
        <div class="markcell"><span>Mark</span><strong>${cents(o.mark ?? o.entry)}</strong></div>
        <div class="markcell"><span>Drift</span><strong class="${drift < 0 ? "down" : "up"}">${(drift > 0 ? "+" : "")}${drift.toFixed(1)}¢</strong></div>
        <div class="markcell"><span>${src.live ? "Unrealized" : "Booked P/L"}</span>
          <strong class="${(un ?? 0) < 0 ? "down" : "up"}">${un == null ? "—" : signed(un)}</strong></div>
      </div>
    </div>
    <div class="board-r">
      <div class="board-tag" style="color:var(--muted)">Mark since entry</div>
      <div class="spark">${sparkSvg(marks, o.entry, 340, 58, (o.mark ?? o.entry) < o.entry ? "var(--lost)" : "var(--won)")}</div>
      <div class="spark-cap">
        <span>fill ${cents(o.entry)}</span>
        <span>now ${cents(o.mark ?? o.entry)}</span>
      </div>
      <div class="eq-note">Dashed line is fill. Onchain USDC is not mixed into Kalshi or Poly cash.</div>
    </div>`;
}

function renderStrip() {
  const s = state.session || {};
  const results = s.results || [];
  const wins = results.filter((r) => r === "W").length;
  const losses = results.filter((r) => r === "L").length;
  const rows = cashRows();
  const allCash = rows.reduce((a, c) => a + Number(c.spendable || 0), 0);
  const ticketCash = rows.filter((c) => !isOnchainRow(c)).reduce((a, c) => a + Number(c.spendable || 0), 0);
  const inPlay = rows.reduce((a, c) => a + Number(c.inPlay || 0), 0);
  const labeled = rows.map((c) => `${c.venue} ${money(c.spendable)}`).join(" · ");
  const sizes = (state.blotter || []).map((t) => t.size).filter((n) => n > 0);
  const avg = sizes.length ? sizes.reduce((a, b) => a + b, 0) / sizes.length : 0;
  const runway = avg ? Math.floor(ticketCash / avg) : 0;
  $("strip").innerHTML = `
    <div class="cell">
      <h3>Realized today</h3>
      <div class="big ${s.realized > 0 ? "pos" : s.realized < 0 ? "neg" : ""}">${signed(s.realized || 0)}</div>
      <div class="sub">${s.fills || 0} fills · ${s.openCount || 0} open</div>
    </div>
    <div class="cell">
      <h3>Record</h3>
      <div class="big">${wins}W ${losses}L</div>
      <div class="wl">${results.map((r) => `<i class="${r === "W" ? "w" : ""}"></i>`).join("")}</div>
      <div class="sub">${results.length ? Math.round((wins / results.length) * 100) : 0}% hit on settled tickets</div>
    </div>
    <div class="cell">
      <h3>Spendable</h3>
      <div class="big">${money(allCash)}</div>
      <div class="sub">${labeled || "—"}</div>
      <div class="sub">${money(inPlay)} in play · Kalshi/Poly runway uses ${money(ticketCash)}</div>
    </div>
    <div class="cell">
      <h3>Runway</h3>
      <div class="big">${runway} tickets</div>
      <div class="sub">Kalshi / Poly US at avg stake ${avg ? money(avg) : "—"}</div>
    </div>`;
}

function renderAccounts() {
  const expected = [
    { match: "polymarket", venue: "Polymarket US", use: "fills", feed: "polymarket" },
    { match: "kalshi", venue: "Kalshi", use: "fills", feed: "kalshi" },
    { match: "onchain", venue: "Onchain", use: "DEX fills", feed: "onchain" },
  ];
  const rows = cashRows();
  const cards = expected.map((ex) => {
    const row = rows.find((c) => (c.venue || "").toLowerCase().includes(ex.match) || c.id === ex.match) || null;
    const feed = feedFor(ex.feed);
    const st = feed ? feed.state : row ? "ok" : "bad";
    const missing = !row;
    const spend = row ? Number(row.spendable || 0) : 0;
    const play = row ? Number(row.inPlay || 0) : 0;
    const addr = row && row.address ? row.address : "";
    const short = addr ? addr.slice(0, 6) + "…" + addr.slice(-4) : "";
    const pol = row && row.pol != null ? Number(row.pol).toFixed(2) + " POL gas (not cash)" : "";
    const verified = row && row.verified ? "chain-verified" : feed ? feed.detail : "";
    return `<div class="acct">
      <div class="acct-h">
        <span class="dot ${st}"></span>
        <h3>${ex.venue}</h3>
        <span class="use">${ex.use}</span>
      </div>
      <div class="big">${missing ? "—" : money(spend)}</div>
      <div class="sub">${missing ? "account not on the live desk payload" : money(play) + " in play"}</div>
      ${addr ? `<div class="acct-addr">${short}${row.network ? " · " + row.network : ""}${row.cash_source ? " · " + row.cash_source : ""}</div>` : ""}
      ${pol ? `<div class="sub">${pol}</div>` : ""}
      ${verified && !missing ? `<div class="sub">${verified}</div>` : ""}
      ${missing ? `<div class="acct-warn">missing from cash[] — check keys on the live desk</div>` : ""}
    </div>`;
  });
  cards.push(`<div class="score-note">Kraken, Unusual Whales, X, and ESPN are scoring feeds, not fill accounts. Global CLOB is not a trading wallet.</div>`);
  $("accounts").innerHTML = cards.join("");
}

function renderBlotter() {
  const rows = state.blotter || [];
  $("blotterCount").textContent = rows.length + " tickets";
  $("blotter").innerHTML = rows
    .map((t) => {
      const cls = t.result === "WON" ? "won" : t.result === "LOST" ? "lost" : "open";
      const plTxt = t.pl == null ? "—" : signed(t.pl);
      const plCls = t.pl == null ? "" : t.pl > 0 ? "up" : "down";
      const edge =
        t.settle == null
          ? t.exit
            ? `<span class="edge">${t.exit}</span>`
            : ""
          : `<span class="edge">${t.exit || (t.settle === 100 ? "settled 100¢" : "settled 0¢")}</span>`;
      return `<tr>
      <td class="t-time num">${t.time}</td>
      <td><span class="t-mkt">${t.market}</span><span class="t-venue">${t.venue}</span></td>
      <td class="r">${t.side}</td>
      <td class="r num">${cents(t.entry)}</td>
      <td class="r num">${money(t.size)}</td>
      <td class="r"><span class="tag ${cls}">${t.result}</span>${edge}</td>
      <td class="r num ${plCls}">${plTxt}</td>
    </tr>`;
    })
    .join("");
}

function renderEquity() {
  const e = (state.session && state.session.equity) || [0];
  const w = 300, h = 96, pad = 8;
  const pts = polyline(e, w, h, pad);
  const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const min = Math.min(...e), max = Math.max(...e), span = max - min || 1;
  const zeroY = pad + (1 - (0 - min) / span) * (h - pad * 2);
  const end = e[e.length - 1];
  const trough = Math.min(...e);
  const troughAt = e.indexOf(trough);
  $("equity").innerHTML = `
    <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Cumulative realized P/L">
      <line x1="0" y1="${zeroY.toFixed(1)}" x2="${w}" y2="${zeroY.toFixed(1)}" stroke="var(--rule)" stroke-width="1"/>
      <path d="${d}" fill="none" stroke="${end >= 0 ? "var(--won)" : "var(--lost)"}" stroke-width="1.75" stroke-linejoin="round"/>
    </svg>`;
  $("eqRange").textContent = e.length + " marks";
  $("eqNote").innerHTML = `Deepest drawdown <span class="down">${signed(trough)}</span> at mark ${troughAt + 1}, now <span class="${end < 0 ? "down" : "up"}">${signed(end)}</span>.`;
}

function renderFeeds() {
  $("feedAge").textContent = state.feedAge || "—";
  $("venues").innerHTML = (state.feeds || [])
    .map(
      (f) => `
    <div class="vrow">
      <span class="dot ${f.state}"></span>
      <span class="vname">${f.name}</span>
      <span class="vstate">${f.detail}</span>
    </div>`
    )
    .join("");
  $("vnote").textContent = state.feedNote || "";
}

function renderDesk() {
  if (!state) return;
  $("clock").textContent = state.clock || "—";
  renderHero();
  renderStrip();
  renderAccounts();
  renderBlotter();
  renderEquity();
  renderFeeds();
}

/* ---------------- Learn: replay live brain.decisions ---------------- */
const STAGES = ["brain", "s1", "s2", "s3", "s4", "s5", "mm", "quiet", "bot", "post", "fill", "watch", "settle", "desk"];
const FEEDS = [
  { id: "s1", key: "whales", name: "Unusual Whales", y: 278 },
  { id: "s2", key: "news", name: "X news + lag", y: 368 },
  { id: "s3", key: "espn", name: "ESPN", y: 458 },
  { id: "s4", key: "crypto", name: "Crypto / Kraken", y: 548 },
  { id: "s5", key: "books", name: "Live books", y: 638 },
];
const POS = {
  score: [425, 465],
  quiet: [425, 632],
  bot: [730, 392],
  post: [730, 528],
  fill: [730, 624],
  watch: [730, 718],
  settle: [730, 814],
  desk: [1023, 586],
  brain: [780, 164],
};

let L = {
  idx: 0,
  step: 0,
  seq: [],
  timeline: [],
  weights: { whales: 0.2, news: 0.2, espn: 0.2, crypto: 0.2, books: 0.2 },
  gate: 6,
  running: true,
  timer: null,
};

function learned() {
  return (state && state.brain && state.brain.learned) || {};
}

function blotterFor(d) {
  return (state.blotter || []).find((r) => r.time === d.time && r.market === d.market) || null;
}

function ticketFrom(d) {
  const row = blotterFor(d);
  const side = (row && row.side) || d.side || "YES";
  const long = side === "YES" || side === "BUY";
  return {
    m: d.market || "quiet cycle",
    v: (row && row.venue) || d.venue || "",
    side,
    long,
    size: row ? row.size : 0,
    entry: row ? row.entry : d.book,
    result: d.result || (row && row.result) || "",
    pl: d.pl != null ? d.pl : row ? row.pl : null,
    why: d.why || "",
    action: d.action,
    model: d.model,
    book: d.book,
    time: d.time,
  };
}

function edgeOf(d) {
  if (d.model == null || d.book == null) return null;
  return d.model - d.book;
}

function clip(s, n) {
  s = String(s || "");
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function seqFor(d) {
  const t = ticketFrom(d);
  const edge = edgeOf(d);
  const why = clip(d.why || d.reason || "", 140);
  const common = [
    {
      focus: FEEDS.map((f) => f.id),
      token: null,
      packets: true,
      text: `${d.time} · live intake: Unusual Whales, X, ESPN, Crypto/Kraken, Kalshi/Poly US/Onchain books`,
    },
    {
      focus: ["mm", "brain"],
      token: POS.score,
      edge,
      action: d.action,
      text:
        d.action === "quiet"
          ? `${d.time} · quiet · ${why || "no ticket"}`
          : `scoring ${t.m} vs ${t.v || "the live book"} · ${why || "gate check"}`,
    },
  ];
  if (d.action === "hold") {
    return common.concat([
      { focus: ["watch"], token: POS.watch, text: `${d.time} · holding ${t.m} — flatten-watch, no new ticket` },
    ]);
  }
  if (d.action !== "fired") {
    return common.concat([
      {
        focus: ["quiet"],
        token: POS.quiet,
        text: `${d.time} · stand down. ${why || "edge under the 6% gate"}. Weights unchanged.`,
      },
    ]);
  }
  return common.concat([
    { focus: ["bot"], token: POS.bot, ticket: true, text: `ticket ${t.side} ${t.m} · ${money(t.size)} · max pay $1.00` },
    { focus: ["post"], token: POS.post, sign: true, text: `signed post to ${t.v || "the venue"}` },
    { focus: ["fill"], token: POS.fill, fill: true, text: `filled ${t.side} ${t.entry != null ? cents(t.entry) : ""} · ${money(t.size)} on ${t.v}` },
    { focus: ["watch"], token: POS.watch, text: `flatten-watch · ${why || "exit armed"}` },
    { focus: ["settle"], token: POS.settle, settle: true, text: `settled ${t.result} ${t.pl == null ? "" : signed(t.pl)} — real P/L, not simulated` },
    { focus: ["desk"], token: POS.desk, book: true, text: `blotter ${t.time} ${t.m} ${t.result} ${t.pl == null ? "" : signed(t.pl)}` },
    { focus: ["brain"], token: POS.brain, ret: true, text: "this settle retunes weights. Quiet cycles do not." },
  ]);
}

function buildWeights() {
  const g = $("weights");
  if (!g || g.childElementCount) return;
  FEEDS.forEach((f, i) => {
    const y = 122 + i * 23;
    const lab = document.createElementNS(NS, "text");
    lab.setAttribute("class", "ts");
    lab.setAttribute("x", 856);
    lab.setAttribute("y", y + 4);
    lab.textContent = f.name;
    g.appendChild(lab);
    const bg = document.createElementNS(NS, "rect");
    bg.setAttribute("class", "bar-bg");
    bg.setAttribute("x", 990);
    bg.setAttribute("y", y - 6);
    bg.setAttribute("width", 100);
    bg.setAttribute("height", 8);
    bg.setAttribute("rx", 4);
    g.appendChild(bg);
    const bar = document.createElementNS(NS, "rect");
    bar.setAttribute("id", "w-" + f.key);
    bar.setAttribute("class", "bar");
    bar.setAttribute("x", 990);
    bar.setAttribute("y", y - 6);
    bar.setAttribute("height", 8);
    bar.setAttribute("rx", 4);
    bar.setAttribute("fill", "#C4B5FD");
    bar.setAttribute("width", 0);
    g.appendChild(bar);
    const val = document.createElementNS(NS, "text");
    val.setAttribute("id", "wv-" + f.key);
    val.setAttribute("class", "lbl");
    val.setAttribute("x", 1100);
    val.setAttribute("y", y + 3);
    g.appendChild(val);
  });
}

function paintWeights() {
  const w = learned().weights || L.weights;
  FEEDS.forEach((f) => {
    const pct = w[f.key] || 0;
    const bar = $("w-" + f.key);
    const lab = $("wv-" + f.key);
    if (bar) bar.setAttribute("width", Math.max(4, pct * 260));
    if (lab) lab.textContent = (pct * 100).toFixed(0) + "%";
  });
  const hit = learned().hit;
  const settled = learned().settled;
  $("k-trades").textContent = settled != null ? settled : "—";
  $("k-hit").textContent = hit != null ? (hit * 100).toFixed(1) + "%" : "—";
  $("k-gate").textContent = (state.brain && state.brain.threshold != null ? state.brain.threshold : 6).toFixed(1) + "%";
}

function stepRevealsTicket() {
  const s = L.seq[L.step] || {};
  return !!(s.settle || s.book || (s.focus && (s.focus.includes("desk") || s.focus.includes("brain"))));
}

function replayedTickets() {
  const out = [];
  L.timeline.forEach((d, i) => {
    if (d.action !== "fired") return;
    if (i < L.idx || (i === L.idx && stepRevealsTicket())) out.push(ticketFrom(d));
  });
  return out;
}

function paintMiniDesk() {
  const sess = state.session || {};
  const shown = replayedTickets();
  const wins = shown.filter((t) => t.result === "WON").length;
  const pnl = shown.reduce((a, t) => a + (Number(t.pl) || 0), 0);
  const eqFull = sess.equity && sess.equity.length ? sess.equity : [0];
  const pts = eqFull.slice(0, Math.max(1, shown.length + 1));
  if ($("k-pnl")) {
    $("k-pnl").textContent = signed(pnl);
    $("k-pnl").setAttribute("fill", pnl >= 0 ? "#2ED47A" : "#FF5C6C");
  }
  if ($("k-win")) $("k-win").textContent = shown.length ? Math.round((wins / shown.length) * 100) + "%" : "—";
  if ($("k-open")) $("k-open").textContent = sess.openCount || 0;

  const x0 = 914, x1 = 1132, y0 = 402, y1 = 476;
  const lo = Math.min(...pts, -1), hi = Math.max(...pts, 1);
  const sx = (i) => (pts.length < 2 ? x0 : x0 + (i / (pts.length - 1)) * (x1 - x0));
  const sy = (v) => y1 - ((v - lo) / (hi - lo || 1)) * (y1 - y0);
  const coords = pts.map((v, i) => sx(i).toFixed(1) + "," + sy(v).toFixed(1));
  if ($("eq-line")) {
    $("eq-line").setAttribute("points", coords.join(" "));
    $("eq-line").setAttribute("stroke", pnl >= 0 ? "#2ED47A" : "#FF5C6C");
  }
  if ($("eq-area")) {
    $("eq-area").setAttribute("d", pts.length > 1 ? "M" + coords.join(" L") + " L" + x1 + "," + y1 + " L" + x0 + "," + y1 + " Z" : "");
  }

  const g = $("rows");
  if (!g) return;
  g.innerHTML = "";
  const rows = shown.slice(-7);
  if ($("blot-empty")) $("blot-empty").style.display = rows.length ? "none" : "block";
  const current = L.timeline[L.idx];
  rows.forEach((r, i) => {
    const y = 590 + i * 36;
    const hot = current && r.time === current.time && r.m === current.market;
    const mk = document.createElementNS(NS, "text");
    mk.setAttribute("class", "ts");
    mk.setAttribute("x", 910);
    mk.setAttribute("y", y);
    mk.setAttribute("fill", hot ? "#E8EEF7" : "#8FA3BC");
    mk.textContent = clip((r.time || "") + " " + (r.m || ""), 32);
    g.appendChild(mk);
    const bd = document.createElementNS(NS, "rect");
    bd.setAttribute("x", 910);
    bd.setAttribute("y", y + 7);
    bd.setAttribute("width", 44);
    bd.setAttribute("height", 18);
    bd.setAttribute("rx", 5);
    bd.setAttribute("fill", r.long ? "#123A28" : "#3A1620");
    g.appendChild(bd);
    const bt = document.createElementNS(NS, "text");
    bt.setAttribute("x", 932);
    bt.setAttribute("y", y + 20);
    bt.setAttribute("text-anchor", "middle");
    bt.setAttribute("font-family", "ui-monospace,monospace");
    bt.setAttribute("font-size", "10");
    bt.setAttribute("fill", r.long ? "#2ED47A" : "#FF5C6C");
    bt.textContent = r.side;
    g.appendChild(bt);
    const sz = document.createElementNS(NS, "text");
    sz.setAttribute("class", "lbl");
    sz.setAttribute("x", 962);
    sz.setAttribute("y", y + 20);
    sz.textContent = money(r.size) + (r.v ? " · " + r.v : "");
    g.appendChild(sz);
    const pl = document.createElementNS(NS, "text");
    pl.setAttribute("x", 1136);
    pl.setAttribute("y", y + 20);
    pl.setAttribute("text-anchor", "end");
    pl.setAttribute("font-family", "ui-monospace,monospace");
    pl.setAttribute("font-size", "12");
    pl.setAttribute("fill", r.pl == null ? "#8FA3BC" : r.pl >= 0 ? "#2ED47A" : "#FF5C6C");
    pl.textContent = r.pl == null ? "—" : signed(r.pl);
    g.appendChild(pl);
  });
}

function paintFeeds() {
  const intake = state.intake || {};
  if ($("f-whales")) $("f-whales").textContent = clip((intake.whales && intake.whales.line) || "tape", 36);
  if ($("f-news")) $("f-news").textContent = clip((intake.news && intake.news.line) || "no pull yet", 36);
  if ($("f-espn")) $("f-espn").textContent = clip((intake.espn && intake.espn.line) || "game state", 36);
  if ($("f-crypto")) $("f-crypto").textContent = clip((intake.crypto && intake.crypto.line) || "Kraken scoring-only", 36);
  if ($("f-books")) $("f-books").textContent = clip((intake.books && intake.books.line) || "Kalshi · Poly US · Onchain", 36);
}

function renderLearnStep() {
  if (!L.seq.length) return;
  const s = L.seq[L.step];
  const d = L.timeline[L.idx];
  const t = d ? ticketFrom(d) : null;
  STAGES.forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.classList.toggle("dim", !s.focus.includes(id));
    el.classList.toggle("hot", s.focus.includes(id));
  });
  const tk = $("token");
  if (tk) {
    if (s.token) {
      tk.setAttribute("opacity", "1");
      tk.style.transform = "translate(" + s.token[0] + "px," + s.token[1] + "px)";
    } else tk.setAttribute("opacity", "0");
  }
  FEEDS.forEach((f, i) => {
    const p = $("pk" + i);
    if (!p) return;
    if (s.packets) {
      p.style.transition = "none";
      p.style.transform = "translate(250px," + f.y + "px)";
      p.style.opacity = "1";
      requestAnimationFrame(() => {
        p.style.transition = "";
        p.style.transform = "translate(300px,465px)";
      });
    } else p.style.opacity = "0";
  });
  $("ret").classList.toggle("live", !!s.ret);
  $("down").classList.toggle("live", s.focus.includes("mm") || !!s.ret);
  const sh = $("shackle");
  if (sh) sh.setAttribute("d", s.sign ? "M8 10 V7 a5 5 0 0 1 10 0 V10" : "M8 10 V6 a5 5 0 0 1 10 -2 V6");
  if (d && d.action !== "fired" && $("tk-market")) {
    $("tk-market").textContent = "no ticket this scan";
    $("tk-side").textContent = "—";
    $("tk-side").setAttribute("fill", "#8FA3BC");
    if ($("tk-badge")) $("tk-badge").setAttribute("fill", "#22334C");
    if ($("tk-size")) $("tk-size").textContent = "$0";
    if ($("tk-note")) $("tk-note").textContent = "max pay $1.00";
    if ($("fill-bar")) $("fill-bar").setAttribute("width", 0);
    if ($("fill-note")) $("fill-note").textContent = "waiting for the book";
    if ($("res-text")) {
      $("res-text").textContent = "—";
      $("res-text").setAttribute("fill", "#8FA3BC");
    }
    if ($("res-badge")) $("res-badge").setAttribute("fill", "#22334C");
  }

  const gate = (state.brain && state.brain.threshold) || 6;
  const gx = 320 + (gate / 15) * 210;
  $("gate-tick").setAttribute("x1", gx);
  $("gate-tick").setAttribute("x2", gx);
  $("gate-lbl").setAttribute("x", gx);
  $("gate-lbl").textContent = "gate " + gate.toFixed(1) + "%";
  if (s.edge !== undefined) {
    if (s.edge == null) {
      $("edge-val").textContent = "—";
      $("edge-bar").setAttribute("width", 0);
      $("verdict").textContent =
        s.action === "fired" ? "fired — edge not on this row, path still ran" : "quiet — no ticket";
    } else {
      $("edge-val").textContent = s.edge.toFixed(1) + "%";
      $("edge-bar").setAttribute("width", Math.min(210, (s.edge / 15) * 210));
      const live = s.edge >= gate;
      $("edge-bar").setAttribute("fill", live ? "#C4B5FD" : "#26313D");
      $("verdict").textContent = live ? "edge clears the gate" : "edge under the gate, no ticket";
    }
  }

  if (s.ticket && t) {
    $("tk-market").textContent = (t.m || "—") + (t.v ? " · " + t.v : "");
    $("tk-side").textContent = t.side;
    $("tk-side").setAttribute("fill", t.long ? "#3FBF7F" : "#E5484D");
    $("tk-badge").setAttribute("fill", t.long ? "#123A28" : "#3A1620");
    $("tk-size").textContent = money(t.size);
    $("tk-note").textContent = "max pay $1.00 · " + (t.v || "Kalshi / Poly US / Onchain");
    $("post-note").textContent = "signed · " + (t.v || "venue");
  }
  if (s.fill && t) {
    $("fill-bar").setAttribute("width", 0);
    requestAnimationFrame(() => $("fill-bar").setAttribute("width", 212));
    $("fill-note").textContent = `${t.side} ${t.entry != null ? cents(t.entry) : ""} · ${money(t.size)} on ${t.v}`;
  }
  if (s.settle && t) {
    const win = t.result === "WON";
    $("res-badge").setAttribute("fill", t.result ? (win ? "#123A28" : "#3A1620") : "#1D262F");
    $("res-text").setAttribute("fill", t.result ? (win ? "#3FBF7F" : "#E5484D") : "#6B7C8C");
    $("res-text").textContent = t.result ? t.result : "—";
  }
  ["syn1", "syn2", "syn3"].forEach((id) => {
    const el = $(id);
    if (el) el.setAttribute("opacity", s.focus.includes("brain") ? "1" : "0.35");
  });
  paintMiniDesk();
  $("status").textContent = s.text;
  $("badge").textContent = `${d ? d.action : "scan"} ${L.idx + 1}/${L.timeline.length || 0}`;
}

function loadTimeline() {
  const raw = ((state.brain && state.brain.decisions) || []).slice();
  L.timeline = raw.slice().reverse();
  if (!L.timeline.length) {
    L.seq = [];
    $("status").textContent = "waiting for live decisions";
    return;
  }
  if (L.idx >= L.timeline.length) L.idx = 0;
  L.seq = seqFor(L.timeline[L.idx]);
  if (L.step >= L.seq.length) L.step = 0;
}

function learnAdvance() {
  if (!L.seq.length) return;
  L.step++;
  if (L.step >= L.seq.length) {
    L.step = 0;
    L.idx = L.timeline.length ? (L.idx + 1) % L.timeline.length : 0;
    if (L.timeline.length) L.seq = seqFor(L.timeline[L.idx]);
  }
  renderLearnStep();
}

function learnTick() {
  if (!L.running) return;
  const d = 2600 - parseInt($("spd").value, 10) * 200;
  L.timer = setTimeout(() => {
    learnAdvance();
    learnTick();
  }, d);
}

function syncLearn() {
  if (!state) return;
  buildWeights();
  paintWeights();
  paintFeeds();
  paintMiniDesk();
  if ($("learn-note")) {
    $("learn-note").textContent =
      (learned().note || "Only settle retunes the brain. Quiet does not.") +
      " Replay walks this session’s real decisions in time order.";
  }
  const before = L.timeline.map((d) => d.time + d.market + d.action).join("|");
  loadTimeline();
  const after = L.timeline.map((d) => d.time + d.market + d.action).join("|");
  if (before !== after) {
    L.idx = 0;
    L.step = 0;
    if (L.timeline.length) L.seq = seqFor(L.timeline[0]);
  }
  if (L.seq.length) renderLearnStep();
}

function setTab(next) {
  tab = next;
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  $("view-desk").classList.toggle("on", tab === "desk");
  $("view-learn").classList.toggle("on", tab === "learn");
  const hash = tab === "learn" ? "#learn" : "#desk";
  if (location.hash !== hash) history.replaceState(null, "", hash);
}

window.addEventListener("hashchange", () => {
  setTab(location.hash === "#learn" ? "learn" : "desk");
});

async function load() {
  try {
    const r = await fetch("/api/desk", { cache: "no-store" });
    if (!r.ok) throw new Error(String(r.status));
    state = await r.json();
    renderDesk();
    syncLearn();
  } catch (err) {
    $("clock").textContent = "desk offline";
  }
}

document.querySelectorAll(".tabs button").forEach((b) => {
  b.addEventListener("click", () => setTab(b.dataset.tab));
});
$("play").addEventListener("click", () => {
  L.running = !L.running;
  if (L.timer) clearTimeout(L.timer);
  $("play").textContent = L.running ? "Pause" : "Play";
  if (L.running) learnTick();
});
$("next").addEventListener("click", () => {
  if (L.timer) clearTimeout(L.timer);
  learnAdvance();
  if (L.running) learnTick();
});
$("reset").addEventListener("click", () => {
  if (L.timer) clearTimeout(L.timer);
  L.idx = 0;
  L.step = 0;
  loadTimeline();
  renderLearnStep();
  if (L.running) learnTick();
});

setTab(tab);
load();
setInterval(load, POLL_MS);
if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  L.running = false;
  $("play").textContent = "Play";
} else {
  learnTick();
}
