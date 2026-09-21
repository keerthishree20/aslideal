// Seller names and titles come from third-party listings, so every piece of text
// goes in through el() / textContent, never innerHTML.

const $ = (id) => document.getElementById(id);
const RING = 2 * Math.PI * 42; // circumference of the gauge circles (r = 42)
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

const KINDS = {
  reference_gap: { label: "Discount from a price nobody charges", short: "M.R.P. nobody charges", icon: "!" },
  real_deal: { label: "Real saving", icon: "✓" },
  going_rate: { label: "Normal price", icon: "=" },
  above_market: { label: "Cheaper elsewhere", icon: "↑" },
  unverified: { label: "Not enough data", icon: "?" },
};

const STEPS = [
  ["amazon_product", "Reading the Amazon.in listing and its M.R.P."],
  ["google_shopping", "Searching Google Shopping India"],
  ["google", "Searching Google India for retailer pages"],
  ["google_immersive_product", "Opening the product to list every store"],
  ["match", "Matching the exact model, filtering listings"],
];

const TRAIL_NAMES = {
  amazon_product: "Read the Amazon.in listing",
  google_shopping: "Searched Google Shopping India",
  google: "Searched Google India",
  google_immersive_product: "Opened a Google product page",
  google_lens: "Looked at the product photo",
  match: "Matched the exact model",
};

// Rejection reasons, in a fixed colour order so a reason keeps its colour between reports.
const REASON_COLOURS = ["#f87171", "#fb923c", "#facc15", "#a78bfa", "#60a5fa", "#94a3b8"];

const EXAMPLES = ["https://www.amazon.in/dp/B0FDFRGWN8", "boAt Airdopes Prime 412", "JBL Tune 520BT", "Philips HL7756 mixer grinder"];

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "style") node.style.cssText = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c != null && c !== false) node.append(c);
  return node;
}

const rupees = (x) => "₹" + Math.round(x).toLocaleString("en-IN");
const pct = (x) => Math.round(x * 100) + "%";
const isAmazon = (seller) => /^amazon/i.test(seller);
const sleep = (ms) => new Promise((r) => setTimeout(r, reduced ? 0 : ms));

function shortName(title, brand = "") {
  let name = title.split(/[,|(:]/)[0].trim();
  if (brand && !name.toLowerCase().startsWith(brand.toLowerCase())) name = brand + " " + name;
  return name.split(/\s+/).slice(0, 6).join(" ");
}

function label(kind, short = false) {
  const k = KINDS[kind] || KINDS.unverified;
  return el("span", { class: "label" }, el("span", { class: "i", "aria-hidden": "true" }, k.icon), short && k.short ? k.short : k.label);
}

function toast(msg, isError = false) {
  const t = el("div", { class: "toast" + (isError ? " error" : ""), role: isError ? "alert" : "status" }, msg);
  $("toasts").append(t);
  setTimeout(() => t.remove(), isError ? 7000 : 3500);
}

async function api(path) {
  const res = await fetch(path);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body;
}

function countUp(node, value, fmt = (n) => Math.round(n).toLocaleString("en-IN")) {
  if (reduced) { node.textContent = fmt(value); return; }
  const start = performance.now(), dur = 1100;
  const tick = (now) => {
    const t = Math.min(1, (now - start) / dur);
    node.textContent = fmt(value * (1 - (1 - t) ** 3));
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// Fill a gauge to `frac` (0..1). The real-saving gauge turns red when Amazon is dearer.
function setRing(circle, frac, negative = false) {
  circle.classList.toggle("neg", negative);
  circle.style.strokeDashoffset = RING;
  requestAnimationFrame(() => requestAnimationFrame(() => {
    circle.style.strokeDashoffset = RING * (1 - Math.max(0, Math.min(1, frac)));
  }));
}

/* ---------- landing ---------- */

async function loadStatus() {
  try {
    const s = await api("/api/status");
    const mode = $("mode");
    mode.hidden = false;
    if (s.demo) {
      mode.textContent = "demo · recorded data";
      mode.title = "No SerpApi key set, so only the recorded products can be checked.";
    } else {
      mode.textContent = s.quota ? `live · ${s.quota.left} searches left` : "live";
      mode.classList.add("live");
    }
  } catch { /* the page works without the status pill */ }
}

let galleryCards = [];

async function loadGallery() {
  try { galleryCards = await api("/api/gallery"); } catch { return; }
  const cards = galleryCards;
  $("gallery").replaceChildren(...cards.map(galleryCard));
  renderFilters(cards);

  countUp(document.querySelector('[data-count="stat-products"]'), cards.length);
  countUp(document.querySelector('[data-count="stat-screened"]'), cards.reduce((n, c) => n + (c.screened || 0), 0));
  countUp(document.querySelector('[data-count="stat-rejected"]'), cards.reduce((n, c) => n + (c.left_out || 0), 0));

  const tryBox = $("try");
  tryBox.replaceChildren(el("span", {}, "Try"), ...cards.filter((c) => c.kind !== "unverified").slice(0, 3).map((c) =>
    el("button", { type: "button", onclick: () => go(c.asin) }, shortName(c.title))));
  tryBox.hidden = false;

  const star = cards.find((c) => c.kind === "reference_gap" && c.claimed_discount >= 0.4) || cards[0];
  if (star) replayConsole(star);
}

function galleryCard(c, i) {
  const real = c.real_discount;
  const card = el("button", {
    class: "card reveal k-" + c.kind, type: "button", "data-kind": c.kind,
    style: `transition-delay:${(i % 4) * 70}ms`, onclick: () => go(c.asin),
  },
    el("div", { class: "card-top" },
      c.thumbnail ? el("img", { src: c.thumbnail, alt: "" }) : null,
      el("div", {}, el("p", { class: "card-brand" }, c.brand), el("p", { class: "card-name" }, shortName(c.title)))),
    label(c.kind, true),
    el("div", { class: "compare" },
      cmpRow("Claimed off", c.claimed_discount, "claim", c.claimed_discount ? pct(c.claimed_discount) : "-"),
      real == null
        ? cmpRow("Real saving", 0, "real", "?")
        : cmpRow(real >= 0 ? "Real saving" : "Above market", Math.abs(real), real >= 0 ? "real" : "real neg",
                 real >= 0 ? pct(real) : "+" + pct(-real))));
  card.addEventListener("pointermove", (e) => {
    const r = card.getBoundingClientRect();
    card.style.setProperty("--mx", e.clientX - r.left + "px");
    card.style.setProperty("--my", e.clientY - r.top + "px");
  });
  return card;
}

function cmpRow(name, frac, cls, text) {
  const fill = el("i");
  requestAnimationFrame(() => setTimeout(() => (fill.style.width = Math.min(frac, 1) * 100 + "%"), 200));
  return el("div", { class: "cmp-row" }, el("span", {}, name), el("div", { class: "cmp-bar " + cls }, fill), el("b", {}, text));
}

function renderFilters(cards) {
  const counts = {};
  for (const c of cards) counts[c.kind] = (counts[c.kind] || 0) + 1;
  const tabs = [["all", "All", cards.length], ...Object.keys(KINDS).filter((k) => counts[k]).map((k) => [k, KINDS[k].short || KINDS[k].label, counts[k]])];
  const box = $("filters");
  box.replaceChildren(...tabs.map(([kind, name, n], i) =>
    el("button", { type: "button", role: "tab", "aria-selected": String(i === 0), onclick: (e) => {
      box.querySelectorAll("button").forEach((b) => b.setAttribute("aria-selected", String(b === e.currentTarget)));
      document.querySelectorAll(".card").forEach((card) => card.classList.toggle("hide", kind !== "all" && card.dataset.kind !== kind));
    } }, name, el("span", { class: "n" }, String(n)))));
}

async function replayConsole(c) {
  let r;
  try { r = await api("/api/check/" + c.asin); } catch { return; }
  const L = r.listing;
  $("c-title").textContent = "check " + L.asin;
  $("c-img").src = L.thumbnail || "";
  $("c-name").textContent = shortName(L.title, L.brand);
  $("c-price").textContent = rupees(L.price);
  $("c-mrp").textContent = L.mrp ? rupees(L.mrp) : "";
  $("c-off").textContent = L.claimed_discount ? pct(L.claimed_discount) + " off" : "";
  $("c-open").onclick = () => go(c.asin);
  const lines = $("c-lines");
  lines.replaceChildren(...(r.trail || []).map((s) =>
    el("li", {}, el("span", {}, el("span", { class: "eng" }, s.engine === "match" ? "match" : s.engine), " ",
      el("span", { class: s.engine === "match" ? "ok" : "" }, s.found)))));
  $("console").hidden = false;
  observeReveal($("console"));
  await sleep(700);
  for (const li of lines.children) { li.classList.add("on"); await sleep(520); }
  $("c-result").classList.add("on");
  const v = r.verdict;
  setRing($("c-ring1"), v.claimed_discount || 0);
  const real = v.real_discount ?? 0;
  setRing($("c-ring2"), Math.abs(real), real < 0);
  countUp($("c-r1"), (v.claimed_discount || 0) * 100, (n) => Math.round(n) + "%");
  countUp($("c-r2"), Math.max(real, 0) * 100, (n) => Math.round(n) + "%");
}

/* ---------- navigation: #check/ASIN ---------- */

function go(asin) {
  if (location.hash === "#check/" + asin) route();
  else location.hash = "check/" + asin;
}

function route() {
  const m = location.hash.match(/^#check\/([A-Z0-9]{10})$/);
  if (m) return runCheck(m[1]);
  $("report").hidden = true;
}

/* ---------- search and check ---------- */

async function onSubmit(e) {
  e.preventDefault();
  const q = $("q").value.trim();
  if (!q) return;
  busy(true);
  $("results").hidden = true;
  try {
    const r = await api("/api/search?q=" + encodeURIComponent(q));
    if (r.asin) return go(r.asin);
    renderResults(r.results);
  } catch (err) {
    toast(err.message, true);
  } finally {
    busy(false);
  }
}

function busy(on) {
  $("go").disabled = on;
  $("go").textContent = on ? "Checking…" : "Check";
}

function renderResults(items) {
  const organic = items.filter((i) => !i.sponsored);
  if (!organic.length) return toast("Amazon.in returned nothing for that. Try the model name, or paste the product link.", true);
  $("results").hidden = false;
  $("result-list").replaceChildren(...organic.slice(0, 10).map((i) =>
    el("li", {},
      el("button", { class: "result", type: "button", onclick: () => go(i.asin) },
        i.thumbnail ? el("img", { src: i.thumbnail, alt: "" }) : el("span"),
        el("span", { class: "t" }, i.title),
        el("span", { class: "p" }, el("b", {}, rupees(i.price)),
          i.mrp ? el("div", {}, el("span", { class: "strike" }, rupees(i.mrp)), " ", el("span", { class: "off" }, pct(i.claimed_discount) + " off")) : null)))));
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

// The progress dialog appears only when a check is slow, i.e. live. A recorded check
// answers in milliseconds and goes straight to the report.
function startProgress() {
  let i = 0;
  const list = $("steps");
  list.replaceChildren(...STEPS.map(([engine, text]) =>
    el("li", {}, el("span", { class: "ic" }), el("span", {}, text, el("code", {}, engine === "match" ? "rules" : engine)))));
  const paint = () => [...list.children].forEach((li, j) => {
    li.className = j < i ? "done" : j === i ? "active" : "";
    li.firstChild.textContent = j < i ? "✓" : "";
  });
  paint();
  const t0 = performance.now();
  const reveal = setTimeout(() => ($("progress").hidden = false), 400);
  const clock = setInterval(() => ($("p-timer").textContent = ((performance.now() - t0) / 1000).toFixed(1) + "s"), 100);
  const steps = setInterval(() => { if (i < STEPS.length - 1) { i++; paint(); } }, 5000);
  return () => { clearTimeout(reveal); clearInterval(clock); clearInterval(steps); $("progress").hidden = true; };
}

async function runCheck(asin) {
  $("results").hidden = true;
  busy(true);
  const stop = startProgress();
  try {
    const r = await api("/api/check/" + encodeURIComponent(asin));
    stop();
    if (r.unavailable) {
      toast(r.error + " Showing listings that do have one.");
      return renderResults(r.suggestions || []);
    }
    renderReport(r);
  } catch (err) {
    stop();
    toast(err.message, true);
  } finally {
    busy(false);
  }
}

/* ---------- report ---------- */

function renderReport(r) {
  const v = r.verdict;
  const L = r.listing;

  $("verdict").className = "panel verdict k-" + v.kind;
  const thumb = $("v-thumb");
  thumb.hidden = !L.thumbnail;
  if (L.thumbnail) thumb.src = L.thumbnail;
  $("v-brand").textContent = L.brand;
  $("v-title").textContent = L.title;
  $("v-price").textContent = rupees(L.price);
  $("v-mrp").textContent = L.mrp ? "M.R.P. " + rupees(L.mrp) : "";
  $("v-link").href = L.link;
  $("v-label").replaceWith(Object.assign(label(v.kind), { id: "v-label" }));
  $("v-headline").textContent = v.headline;
  $("v-notes").replaceChildren(...v.notes.map((n) => el("li", {}, n)));

  $("report").hidden = false;
  $("report").scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });

  // gauges
  setRing($("g1"), v.claimed_discount || 0);
  countUp($("g1-t"), (v.claimed_discount || 0) * 100, (n) => Math.round(n) + "%");
  const real = v.real_discount;
  if (real == null) {
    setRing($("g2"), 0);
    $("g2-t").textContent = "?";
    $("g2-cap").textContent = "too few other sellers";
  } else {
    setRing($("g2"), Math.abs(real), real < 0);
    countUp($("g2-t"), Math.abs(real) * 100, (n) => (real < 0 ? "+" : "") + Math.round(n) + "%");
    $("g2-cap").textContent = real >= 0 ? "cheaper than other stores" : "more than other stores";
  }
  $("s-street").textContent = v.street_price ? rupees(v.street_price) : "-";
  $("s-street-sub").textContent = v.street_price
    ? `median of ${v.sellers_used} other in-stock seller${v.sellers_used === 1 ? "" : "s"}`
    : "needs 2 or more other sellers";

  renderChart(v, r.offers);
  renderPatterns(r.signals);
  renderHistory(r);
  lastReport = r;
  renderTable(r.offers);
  renderTrail(r.trail || []);
  renderFunnel(r);
}

let lastReport = null;

const PATTERN_NAMES = {
  inflated_reference: "Inflated reference price",
  false_urgency: "False urgency",
  drip_pricing: "Drip pricing",
  conditional_savings: "Savings only some buyers get",
};

// Three of the thirteen dark patterns India's CCPA named in 2023 show up in price
// data. The wording reports what was seen, never what anyone intended.
function renderPatterns(sig) {
  const panel = $("patterns");
  panel.hidden = !sig;
  if (!sig) return;
  $("pattern-list").replaceChildren(...Object.entries(sig.checks).map(([key, c]) => {
    const state = c.flag === true ? ["flag", "flagged"] : c.flag === false ? ["ok", "clear"] : ["na", "no data"];
    return el("li", {},
      el("span", { class: "pchip " + state[0] }, state[1]),
      el("div", {}, el("b", {}, PATTERN_NAMES[key] || key), el("p", {}, c.detail)));
  }));

  const complaints = sig.complaints || [];
  $("complaints-panel").hidden = !complaints.length;
  if (!complaints.length) return;
  $("complaints").replaceChildren(...complaints.map((c) => {
    const fill = el("i", { style: "width:0;background:var(--over)" });
    requestAnimationFrame(() => setTimeout(() => (fill.style.width = Math.round(c.share * 100) + "%"), 150));
    return el("div", { class: "reason", style: "grid-template-columns:1fr auto" },
      el("span", {}, `${c.topic}: ${c.negative} of ${c.total.toLocaleString("en-IN")} mentions are negative`),
      el("b", {}, Math.round(c.share * 100) + "%"),
      el("div", { class: "bar", style: "grid-column:1/-1" }, fill));
  }));
}

// Scanning a search: how many of the advertised deals hold up?
async function onScan(e) {
  e.preventDefault();
  const q = $("scan-q").value.trim();
  if (!q) return;
  const btn = $("scan-go");
  btn.disabled = true; btn.textContent = "Scanning…";
  $("scan-headline").hidden = true;
  $("scan-results").hidden = true;
  $("scan-csv").hidden = true;
  try {
    const r = await api(`/api/scan?q=${encodeURIComponent(q)}&limit=${$("scan-n").value}`);
    $("scan-headline").textContent = r.headline;
    $("scan-headline").hidden = false;
    // The CSV is the same scan again, answered from the cache, so it costs nothing extra.
    const csv = $("scan-csv");
    csv.href = `/api/scan.csv?q=${encodeURIComponent(q)}&limit=${$("scan-n").value}`;
    csv.hidden = false;
    $("scan-rows").replaceChildren(...r.rows.map((row) => {
      const kind = KINDS[row.kind] || { label: row.headline || "couldn't check", icon: "?" };
      return el("tr", {},
        el("td", {}, el("a", { href: "#check/" + row.asin, title: row.title }, shortName(row.title, row.brand))),
        el("td", { class: "num" }, rupees(row.price)),
        el("td", { class: "num" }, row.claimed_discount ? pct(row.claimed_discount) : "-"),
        el("td", { class: "num" }, row.real_discount == null ? "?" : pct(row.real_discount)),
        el("td", { class: "kind" }, kind.short || kind.label));
    }));
    $("scan-results").hidden = false;
    $("scan-results").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false; btn.textContent = "Scan";
  }
}

// A photo of a product: Google Lens names it, then we look it up on Amazon.in.
async function onLens(e) {
  e.preventDefault();
  const url = $("lens-url").value.trim();
  if (!url) return;
  const btn = e.target.querySelector("button");
  btn.disabled = true; btn.textContent = "Looking…";
  try {
    const r = await api("/api/lens?url=" + encodeURIComponent(url));
    toast(`Google Lens says: ${r.recognised}`);
    renderResults(r.results);
    if (r.seen_at && r.seen_at.length) {
      const list = el("ul", { class: "sightings" },
        el("li", { class: "muted" }, "Lens also priced it at:"),
        ...r.seen_at.map((x) => el("li", {}, el("span", {}, x.source), el("b", {}, rupees(x.price)))));
      $("result-list").before(list);
      setTimeout(() => list.remove(), 60000);
    }
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false; btn.textContent = "Identify";
  }
}

// SerpApi has no price history, so the app keeps its own: one row per live check.
function renderHistory(r) {
  const days = r.history || [];
  const panel = $("history-panel");
  panel.hidden = !days.length;
  if (!days.length) return;
  const first = days[0], last = days[days.length - 1];
  const moved = (a, b) => (a == null || b == null ? null : Math.round(b - a));
  const bits = [];
  if (days.length === 1) {
    bits.push(`First reading today. Check this product again another day and the movement shows up here.`);
  } else {
    const p = moved(first.price, last.price), st = moved(first.street_price, last.street_price);
    bits.push(`${days.length} readings since ${first.date}.`);
    bits.push(p ? `Amazon's price ${p > 0 ? "rose" : "fell"} by ${rupees(Math.abs(p))}.` : "Amazon's price hasn't moved.");
    if (st) bits.push(`Other stores ${st > 0 ? "rose" : "fell"} by ${rupees(Math.abs(st))}.`);
    if (moved(first.mrp, last.mrp)) bits.push(`The M.R.P. itself changed — worth a closer look.`);
  }
  $("history-note").textContent = bits.join(" ");
  $("history-rows").replaceChildren(...days.slice().reverse().map((d) =>
    el("tr", {},
      el("td", {}, d.date),
      el("td", { class: "num" }, rupees(d.price)),
      el("td", { class: "num" }, d.mrp ? rupees(d.mrp) : "-"),
      el("td", { class: "num" }, d.street_price ? rupees(d.street_price) : "-"),
      el("td", { class: "num" }, d.claimed_discount ? pct(d.claimed_discount) : "-"),
      el("td", {}, (KINDS[d.kind] || KINDS.unverified).short || (KINDS[d.kind] || KINDS.unverified).label))));
}

// A 1200x630 card of the verdict, drawn on a canvas so it can be saved and shared.
function saveCard() {
  if (!lastReport) return;
  const { listing: L, verdict: v } = lastReport;
  const c = el("canvas", { width: "1200", height: "630" });
  const g = c.getContext("2d");
  g.fillStyle = "#0b0c11"; g.fillRect(0, 0, 1200, 630);
  const glow = g.createRadialGradient(980, 120, 40, 980, 120, 520);
  glow.addColorStop(0, "rgba(255,122,46,.35)"); glow.addColorStop(1, "rgba(255,122,46,0)");
  g.fillStyle = glow; g.fillRect(0, 0, 1200, 630);

  g.fillStyle = "#ff7a2e"; g.font = "700 30px Space Grotesk, sans-serif";
  g.fillText("AsliDeal", 64, 86);
  g.fillStyle = "#8a8fa0"; g.font = "400 20px Inter, sans-serif";
  g.fillText("Is that \u201c% off\u201d actually asli?", 190, 86);

  const kind = KINDS[v.kind] || KINDS.unverified;
  const colour = { reference_gap: "#fbbf24", real_deal: "#34d399", going_rate: "#60a5fa", above_market: "#f87171", unverified: "#a1a7b6" }[v.kind];
  g.fillStyle = colour; g.font = "700 22px Inter, sans-serif";
  g.fillText(kind.label.toUpperCase(), 64, 150);

  g.fillStyle = "#eceef4"; g.font = "600 40px Space Grotesk, sans-serif";
  wrapText(g, shortName(L.title, L.brand), 64, 215, 1070, 50, 2);

  g.font = "700 108px Space Grotesk, sans-serif"; g.fillStyle = "#ff9b5c";
  g.fillText(v.claimed_discount ? pct(v.claimed_discount) : "-", 64, 400);
  g.font = "400 20px Inter, sans-serif"; g.fillStyle = "#8a8fa0";
  g.fillText("Amazon's \u201c% off\u201d", 68, 435);

  g.font = "400 40px Inter, sans-serif"; g.fillStyle = "#5b6072";
  g.fillText("vs", 330, 390);

  const real = v.real_discount;
  g.font = "700 108px Space Grotesk, sans-serif";
  g.fillStyle = real == null ? "#a1a7b6" : real < 0 ? "#f87171" : "#34e0a1";
  g.fillText(real == null ? "?" : real >= 0 ? pct(real) : "+" + pct(-real), 420, 400);
  g.font = "400 20px Inter, sans-serif"; g.fillStyle = "#8a8fa0";
  g.fillText(real == null ? "not enough sellers" : "real saving vs other stores", 424, 435);

  g.fillStyle = "#c3c7d3"; g.font = "400 24px Inter, sans-serif";
  wrapText(g, v.headline, 64, 500, 1070, 34, 2);

  g.fillStyle = "#5b6072"; g.font = "400 18px Inter, sans-serif";
  g.fillText("github.com/keerthishree20/aslideal  ·  prices checked " + new Date().toLocaleDateString("en-IN"), 64, 590);

  c.toBlob((blob) => {
    const url = URL.createObjectURL(blob);
    const a = el("a", { href: url, download: `aslideal-${L.asin}.png` });
    document.body.append(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    toast("Image saved.");
  });
}

function wrapText(g, text, x, y, maxWidth, lineHeight, maxLines) {
  const words = String(text).split(/\s+/);
  let line = "", lines = 0;
  for (const w of words) {
    const test = line ? line + " " + w : w;
    if (g.measureText(test).width > maxWidth && line) {
      lines += 1;
      if (lines === maxLines) { g.fillText(line.replace(/[.,]$/, "") + "\u2026", x, y); return; }
      g.fillText(line, x, y); y += lineHeight; line = w;
    } else line = test;
  }
  g.fillText(line, x, y);
}

function niceTicks(lo, hi, count) {
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
  const out = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) out.push(t);
  return out;
}

function renderChart(v, offers) {
  const chart = $("chart");
  const prices = offers.map((o) => o.price).concat([v.price]);
  if (v.mrp) prices.push(v.mrp);
  let lo = Math.min(...prices), hi = Math.max(...prices);
  const pad = (hi - lo) * 0.08 || hi * 0.1;
  lo = Math.max(0, lo - pad); hi += pad;
  const x = (p) => ((p - lo) / (hi - lo)) * 100;

  const rows = [...offers];
  if (!rows.some((o) => isAmazon(o.seller))) rows.push({ seller: "Amazon.in", price: v.price, in_stock: true, title: "", link: "", logo: "" });
  rows.sort((a, b) => a.price - b.price);

  const axis = el("div", { class: "c-axis" }, el("span"),
    el("div", { class: "c-plot" }, ...niceTicks(lo, hi, innerWidth < 600 ? 2 : 5).map((t) => el("span", { class: "c-tick", style: `left:${x(t)}%` }, rupees(t)))),
    el("span"));

  // The legend carries the values too; on a phone the in-chart labels are hidden for lack of room.
  $("lg-street").textContent = v.street_price ? "Street price " + rupees(v.street_price) : "Street price";
  $("lg-mrp").textContent = v.mrp ? "M.R.P. " + rupees(v.mrp) : "M.R.P.";
  const refs = [];
  if (v.street_price) refs.push(["ref-street", v.street_price, "Street " + rupees(v.street_price)]);
  if (v.mrp) refs.push(["ref-mrp", v.mrp, "M.R.P. " + rupees(v.mrp)]);
  const close = refs.length === 2 && Math.abs(x(refs[0][1]) - x(refs[1][1])) < 18;
  const lines = el("div", { class: "c-lines" }, ...refs.map(([cls, p, text], i) => {
    let edge = x(p) > 85 ? " edge-r" : x(p) < 12 ? " edge-l" : "";
    if (close) edge = i === 0 ? " edge-r" : " edge-l"; // two labels close together splay apart
    return el("div", { class: `c-line ${cls}${edge}`, style: `left:${x(p)}%` }, el("span", {}, text));
  }));

  const dots = [];
  const body = el("div", {}, ...rows.map((o) => {
    const own = isAmazon(o.seller);
    const dot = el("div", { class: "c-dot" });
    dots.push([dot, x(o.price)]);
    const row = el("div", { class: "c-row" + (own ? " own" : "") + (o.in_stock ? "" : " out"), tabindex: "0" },
      el("div", { class: "c-seller" },
        o.logo ? el("img", { src: o.logo, alt: "", loading: "lazy" }) : null,
        el("span", { class: "nm" }, own ? "Amazon.in" : o.seller),
        o.in_stock ? null : el("span", { class: "oos-tag" }, "out of stock")),
      el("div", { class: "c-plot" }, el("div", { class: "c-track" }), dot),
      el("div", { class: "c-price" }, rupees(o.price)));
    row.addEventListener("pointerenter", (e) => tip(e, o));
    row.addEventListener("pointermove", (e) => tip(e, o));
    row.addEventListener("pointerleave", () => ($("tip").hidden = true));
    return row;
  }));

  chart.replaceChildren(el("div", { class: "c-space" }), axis, body, lines);
  // Dots start at the left edge and slide to their price.
  requestAnimationFrame(() => requestAnimationFrame(() => dots.forEach(([d, left]) => (d.style.left = left + "%"))));
}

function tip(e, o) {
  const t = $("tip");
  const stock = o.in_stock ? "In stock" : "Out of stock, not counted";
  t.replaceChildren(el("b", {}, `${o.seller} · ${rupees(o.price)}`), stock, o.title ? el("div", {}, o.title) : null);
  t.hidden = false;
  const box = t.parentElement.getBoundingClientRect();
  t.style.left = Math.min(e.clientX - box.left + 14, box.width - t.offsetWidth - 10) + "px";
  t.style.top = e.clientY - box.top + 16 + "px";
}

function link(o) {
  if (!/^https?:\/\//.test(o.link || "")) return o.title;
  return el("a", { href: o.link, target: "_blank", rel: "noopener nofollow", title: o.title }, o.title);
}

function renderTable(offers) {
  const rows = offers.map((o) => el("tr", {},
    el("td", {}, o.seller),
    el("td", { class: "num" }, rupees(o.price)),
    el("td", { class: o.in_stock ? "" : "oos" }, o.in_stock ? "In stock" : "Out of stock"),
    el("td", { class: "ttl" }, link(o))));
  $("seller-rows").replaceChildren(...(rows.length ? rows : [el("tr", {}, el("td", { colspan: "4", class: "muted" }, "No matching listings found."))]));
}

function renderTrail(trail) {
  $("trail").replaceChildren(...trail.map((s, i) =>
    el("li", { class: i === trail.length - 1 ? "final" : "", style: `animation-delay:${i * 90}ms` },
      el("span", { class: "node" }, String(i + 1).padStart(2, "0")),
      el("div", {},
        el("code", {}, s.engine === "match" ? "same-model rules" : s.engine),
        el("p", { class: "what" }, TRAIL_NAMES[s.engine] || s.engine),
        el("p", { class: "found" }, s.found),
        s.query ? el("p", { class: "q", title: s.query }, (s.engine === "match" ? "model: " : "q: ") + s.query) : null))));
}

function renderFunnel(r) {
  const kept = r.offers.length, out = r.rejected.length, found = kept + out;
  const fn = (cls, n, text) => {
    const b = el("b", {}, "0");
    countUp(b, n);
    return el("div", { class: "fn " + cls }, b, el("span", {}, text));
  };
  $("funnel").replaceChildren(fn("", found, "listings found"), fn("kept", kept, "same product"), fn("out", out, "left out"));

  const last = (r.trail || []).find((s) => s.engine === "match");
  const reasons = Object.entries(last ? last.reasons : {});
  const segs = [["same product, kept", kept, "var(--real)"], ...reasons.map(([why, n], i) => [why, n, REASON_COLOURS[i % REASON_COLOURS.length]])];
  const stack = el("div", { class: "stack", role: "img", "aria-label": segs.map(([w, n]) => `${n} ${w}`).join(", ") },
    ...segs.map(([, , colour]) => el("i", { style: `background:${colour}` })));
  requestAnimationFrame(() => requestAnimationFrame(() =>
    [...stack.children].forEach((seg, i) => (seg.style.flexGrow = String(segs[i][1])))));
  $("reasons").replaceChildren(stack, ...segs.map(([why, n, colour]) =>
    el("div", { class: "reason" }, el("span", { class: "sw", style: `background:${colour}` }), el("span", {}, why[0].toUpperCase() + why.slice(1)), el("b", {}, String(n)))));

  $("rejected-box").hidden = !out;
  $("rejected-sum").textContent = `See all ${out} left-out listing${out === 1 ? "" : "s"}`;
  $("rejected-rows").replaceChildren(...r.rejected.map((o) =>
    el("tr", {},
      el("td", {}, o.seller),
      el("td", { class: "num" }, rupees(o.price)),
      el("td", {}, o.reason),
      el("td", { class: "ttl" }, link(o)))));
}

/* ---------- polish ---------- */

const revealer = "IntersectionObserver" in window
  ? new IntersectionObserver((entries) => entries.forEach((en) => {
      if (en.isIntersecting) { en.target.classList.add("in"); revealer.unobserve(en.target); }
    }), { threshold: 0.12 })
  : null;

function observeReveal(root = document) {
  const nodes = root.classList && root.classList.contains("reveal") ? [root] : root.querySelectorAll(".reveal:not(.in)");
  nodes.forEach((n) => (revealer ? revealer.observe(n) : n.classList.add("in")));
}

// Example queries type themselves into the empty search box.
async function typePlaceholder() {
  if (reduced) return;
  const input = $("q");
  for (let k = 0; ; k = (k + 1) % EXAMPLES.length) {
    const text = EXAMPLES[k];
    for (let i = 1; i <= text.length; i++) { input.placeholder = text.slice(0, i); await sleep(45); }
    await sleep(1800);
    for (let i = text.length; i >= 0; i--) { input.placeholder = text.slice(0, i); await sleep(18); }
    await sleep(300);
  }
}

document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement !== $("q")) { e.preventDefault(); $("q").focus(); }
});
$("form").addEventListener("submit", onSubmit);
$("scan-form").addEventListener("submit", onScan);
$("lens-form").addEventListener("submit", onLens);
$("back").addEventListener("click", () => {
  history.pushState("", "", location.pathname);
  $("report").hidden = true;
  $("checks").scrollIntoView({ behavior: "smooth" });
});
$("save").addEventListener("click", saveCard);
$("copy").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(location.href); toast("Report link copied."); }
  catch { toast("Couldn't copy. The link is in the address bar.", true); }
});
$("home-link").addEventListener("click", (e) => {
  e.preventDefault();
  history.pushState("", "", location.pathname);
  $("report").hidden = true;
  scrollTo({ top: 0, behavior: "smooth" });
});
window.addEventListener("hashchange", route);

loadStatus();
loadGallery().then(() => observeReveal());
observeReveal();
typePlaceholder();
route();
