// Seller names and titles come from third-party listings, so every piece of text
// goes in through el() / textContent, never innerHTML.

const $ = (id) => document.getElementById(id);

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
  ["match", "Matching the exact model and filtering listings"],
];

const TRAIL_NAMES = {
  amazon_product: "Read the Amazon.in listing",
  google_shopping: "Searched Google Shopping India",
  google: "Searched Google India",
  google_immersive_product: "Opened a Google product page",
  match: "Matched the exact model",
};

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

function shortName(title, brand = "") {
  let name = title.split(/[,|(:]/)[0].trim();
  if (brand && !name.toLowerCase().startsWith(brand.toLowerCase())) name = brand + " " + name;
  return name.split(/\s+/).slice(0, 6).join(" ");
}

function label(kind, short = false) {
  const k = KINDS[kind] || KINDS.unverified;
  return el("span", { class: "label" }, el("span", { class: "i", "aria-hidden": "true" }, k.icon),
    short && k.short ? k.short : k.label);
}

function show(msg, isError = false) {
  const m = $("msg");
  m.hidden = !msg;
  m.textContent = msg || "";
  m.classList.toggle("error", isError);
}

async function api(path) {
  const res = await fetch(path);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body;
}

/* ---------- landing ---------- */

async function loadStatus() {
  try {
    const s = await api("/api/status");
    const mode = $("mode");
    mode.hidden = false;
    if (s.demo) {
      mode.textContent = "Demo · recorded data";
      mode.title = "No SerpApi key set, so only the products below can be checked.";
    } else {
      mode.textContent = s.quota ? `Live · ${s.quota.left} searches left` : "Live";
      mode.classList.add("live");
    }
  } catch { /* the page works without the status chip */ }
}

async function loadGallery() {
  let cards = [];
  try { cards = await api("/api/gallery"); } catch { return; }
  $("gallery").replaceChildren(...cards.map((c, i) => galleryCard(c, i)));
  const star = cards.find((c) => c.kind === "reference_gap" && c.claimed_discount >= 0.4) || cards[0];
  if (star) teaser(star);
}

function galleryCard(c, i) {
  const real = c.real_discount == null ? null : c.real_discount;
  return el("button", {
      class: "g-card k-" + c.kind, type: "button", style: `animation-delay:${i * 60}ms`,
      onclick: () => go(c.asin),
    },
    el("div", { class: "g-top" },
      c.thumbnail ? el("img", { src: c.thumbnail, alt: "" }) : null,
      el("div", {},
        el("p", { class: "g-brand" }, c.brand),
        el("p", { class: "g-name" }, shortName(c.title)))),
    label(c.kind, true),
    el("div", { class: "g-nums" },
      el("div", { class: "g-num claim" }, el("b", {}, c.claimed_discount ? pct(c.claimed_discount) : "-"), el("span", {}, "claimed off")),
      el("div", { class: "g-num real" },
        el("b", {}, real == null ? "?" : real >= 0 ? pct(real) : "+" + pct(-real)),
        el("span", {}, real == null ? "too few sellers" : real >= 0 ? "real saving" : "above market"))));
}

function teaser(c) {
  $("t-img").src = c.thumbnail || "";
  $("t-name").textContent = shortName(c.title, c.brand);
  $("t-mrp").textContent = c.mrp ? rupees(c.mrp) : "";
  $("t-price").textContent = rupees(c.price);
  $("t-claimed").textContent = pct(c.claimed_discount);
  $("t-real").textContent = pct(Math.max(c.real_discount || 0, 0));
  $("t-line").textContent = c.street_price
    ? `${c.sellers} other Indian stores sell it for about ${rupees(c.street_price)}. None charge the ${rupees(c.mrp)} M.R.P.`
    : "";
  $("t-open").onclick = () => go(c.asin);
  $("teaser").hidden = false;
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
  $("progress").hidden = true;
  $("gallery-box").hidden = false;
}

/* ---------- search and check ---------- */

async function onSubmit(e) {
  e.preventDefault();
  const q = $("q").value.trim();
  if (!q) return;
  busy(true);
  $("results").hidden = true;
  show("");
  try {
    const r = await api("/api/search?q=" + encodeURIComponent(q));
    if (r.asin) return go(r.asin);
    renderResults(r.results);
  } catch (err) {
    show(err.message, true);
  } finally {
    busy(false);
  }
}

function busy(on) {
  const b = $("form").querySelector("button");
  b.disabled = on;
  b.textContent = on ? "Checking…" : "Check discount";
}

function renderResults(items) {
  const organic = items.filter((i) => !i.sponsored);
  if (!organic.length) return show("Amazon.in returned nothing for that. Try the model name, or paste the product link.", true);
  $("results").hidden = false;
  $("result-list").replaceChildren(...organic.slice(0, 10).map((i) =>
    el("li", {},
      el("button", { class: "result", type: "button", onclick: () => go(i.asin) },
        i.thumbnail ? el("img", { src: i.thumbnail, alt: "" }) : el("span"),
        el("span", { class: "t" }, i.title),
        el("span", { class: "p" },
          el("b", {}, rupees(i.price)),
          i.mrp ? el("div", {}, el("span", { class: "strike" }, rupees(i.mrp)), " ", el("span", { class: "off" }, pct(i.claimed_discount) + " off")) : null)))));
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

let stepTimer = null;

function startSteps() {
  // Shown only if the check is slow (a live one); a recorded one answers instantly.
  let i = 0;
  const list = $("steps");
  list.replaceChildren(...STEPS.map(([engine, text]) =>
    el("li", {}, el("span", { class: "ic" }), el("span", {}, text, " ", el("code", {}, engine === "match" ? "same-model rules" : engine)))));
  const paint = () => [...list.children].forEach((li, j) => {
    li.className = j < i ? "done" : j === i ? "active" : "";
    li.firstChild.textContent = j < i ? "✓" : "";
  });
  const reveal = setTimeout(() => {
    $("progress").hidden = false;
    $("progress").scrollIntoView({ behavior: "smooth", block: "center" });
  }, 350);
  paint();
  stepTimer = setInterval(() => { if (i < STEPS.length - 1) { i++; paint(); } }, 5000);
  return () => { clearTimeout(reveal); clearInterval(stepTimer); $("progress").hidden = true; };
}

async function runCheck(asin) {
  $("results").hidden = true;
  $("report").hidden = true;
  show("");
  busy(true);
  const stop = startSteps();
  try {
    const r = await api("/api/check/" + encodeURIComponent(asin));
    stop();
    renderReport(r);
  } catch (err) {
    stop();
    show(err.message, true);
  } finally {
    busy(false);
  }
}

/* ---------- report ---------- */

function renderReport(r) {
  const v = r.verdict;
  const L = r.listing;
  $("gallery-box").hidden = true;

  $("verdict").className = "verdict k-" + v.kind;
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

  // score tiles
  $("s-claimed").textContent = v.claimed_discount ? pct(v.claimed_discount) : "-";
  $("s-claimed-sub").textContent = v.mrp ? `"% off" from M.R.P. ${rupees(v.mrp)}` : "no M.R.P. shown";
  const real = v.real_discount;
  $("s-real").textContent = real == null ? "?" : real >= 0 ? pct(real) : "+" + pct(-real);
  $("s-real-sub").textContent = real == null ? "not enough other sellers to say"
    : real >= 0 ? "cheaper than other stores" : "more than other stores";
  $("s-street").textContent = v.street_price ? rupees(v.street_price) : "-";
  $("s-street-sub").textContent = v.street_price
    ? `median of ${v.sellers_used} other in-stock seller${v.sellers_used === 1 ? "" : "s"}`
    : "needs 2 or more other sellers";
  $("v-notes").replaceChildren(...v.notes.map((n) => el("li", {}, n)));

  renderChart(v, r.offers);
  renderTable(r.offers);
  renderTrail(r.trail || []);
  renderRejected(r);

  $("report").hidden = false;
  $("report").scrollIntoView({ behavior: "smooth", block: "start" });
}

function niceTicks(lo, hi, count = 5) {
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
    el("div", { class: "c-plot" }, ...niceTicks(lo, hi, window.innerWidth < 600 ? 2 : 5).map((t) => el("span", { class: "c-tick", style: `left:${x(t)}%` }, rupees(t)))),
    el("span"));

  const refs = [];
  if (v.street_price) refs.push(["street", v.street_price, "Street " + rupees(v.street_price)]);
  if (v.mrp) refs.push(["mrp", v.mrp, "M.R.P. " + rupees(v.mrp)]);
  // The legend carries the values too: on a phone the in-chart labels are hidden for lack of room.
  $("lg-street").textContent = v.street_price ? "Street price " + rupees(v.street_price) : "Street price";
  $("lg-mrp").textContent = v.mrp ? "M.R.P. " + rupees(v.mrp) : "M.R.P.";
  const close = refs.length === 2 && Math.abs(x(refs[0][1]) - x(refs[1][1])) < 18;
  const lines = el("div", { class: "c-lines" }, ...refs.map(([cls, p, text], i) => {
    let edge = x(p) > 85 ? " edge-r" : x(p) < 12 ? " edge-l" : "";
    if (close) edge = i === 0 ? " edge-r" : " edge-l";  // two labels close together splay apart
    return el("div", { class: `c-line ${cls}${edge}`, style: `left:${x(p)}%` }, el("span", {}, text));
  }));

  const body = el("div", { class: "c-rows" }, ...rows.map((o) => {
    const own = isAmazon(o.seller);
    const row = el("div", { class: "c-row" + (own ? " own" : "") + (o.in_stock ? "" : " out"), tabindex: "0" },
      el("div", { class: "c-seller" },
        o.logo ? el("img", { src: o.logo, alt: "", loading: "lazy" }) : null,
        el("span", { class: "nm" }, own ? "Amazon.in" : o.seller),
        o.in_stock ? null : el("span", { class: "oos-tag" }, "out of stock")),
      el("div", { class: "c-plot" }, el("div", { class: "c-track" }), el("div", { class: "c-dot", style: `left:${x(o.price)}%` })),
      el("div", { class: "c-price" }, rupees(o.price)));
    row.addEventListener("mouseenter", (e) => tip(e, o));
    row.addEventListener("mousemove", (e) => tip(e, o));
    row.addEventListener("mouseleave", () => ($("tip").hidden = true));
    return row;
  }));

  chart.replaceChildren(el("div", { style: "height:30px" }), axis, body, lines);
}

function tip(e, o) {
  const t = $("tip");
  const stock = o.in_stock ? "In stock" : "Out of stock, not counted";
  t.replaceChildren(el("b", {}, `${o.seller} · ${rupees(o.price)}`), stock, o.title ? el("div", {}, o.title) : null);
  t.hidden = false;
  const card = t.parentElement.getBoundingClientRect();
  const left = Math.min(e.clientX - card.left + 14, card.width - t.offsetWidth - 10);
  t.style.left = left + "px";
  t.style.top = e.clientY - card.top + 16 + "px";
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
    el("li", { class: i === trail.length - 1 ? "final" : "" },
      el("span", { class: "dot" }, String(i + 1)),
      el("div", {},
        el("span", { class: "eng" }, el("code", {}, s.engine === "match" ? "same-model rules" : s.engine)),
        el("p", { class: "what" }, TRAIL_NAMES[s.engine] || s.engine),
        el("p", { class: "found" }, s.found),
        s.query ? el("p", { class: "q", title: s.query }, (s.engine === "match" ? "model: " : "query: ") + s.query) : null))));
}

function renderRejected(r) {
  const rej = r.rejected;
  const last = (r.trail || []).find((s) => s.engine === "match");
  const reasons = Object.entries(last ? last.reasons : {});
  const max = Math.max(1, ...reasons.map(([, n]) => n));
  $("reasons").replaceChildren(...(reasons.length ? reasons.map(([why, n]) =>
    el("div", { class: "reason" },
      el("span", {}, why[0].toUpperCase() + why.slice(1)),
      el("b", {}, String(n)),
      el("div", { class: "bar" }, el("i", { style: `width:${(n / max) * 100}%` }))))
    : [el("p", { class: "muted small" }, "Nothing was left out.")]));
  $("rejected-box").hidden = !rej.length;
  $("rejected-sum").textContent = `See all ${rej.length} listing${rej.length === 1 ? "" : "s"}`;
  $("rejected-rows").replaceChildren(...rej.map((o) =>
    el("tr", {},
      el("td", {}, o.seller),
      el("td", { class: "num" }, rupees(o.price)),
      el("td", {}, o.reason),
      el("td", { class: "ttl" }, link(o)))));
}

/* ---------- wiring ---------- */

$("form").addEventListener("submit", onSubmit);
$("back").addEventListener("click", () => { location.hash = ""; window.scrollTo({ top: 0, behavior: "smooth" }); });
window.addEventListener("hashchange", route);
loadStatus();
loadGallery();
route();
