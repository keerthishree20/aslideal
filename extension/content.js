// Puts an AsliDeal verdict panel on an Amazon.in product page.
// Everything is drawn inside a shadow root so Amazon's CSS can't reach it,
// and every piece of text goes in through textContent.

const ASIN_IN_URL = /\/(?:dp|gp\/product|product)\/([A-Z0-9]{10})/;
const KINDS = {
  reference_gap: { label: "Discount from a price nobody charges", icon: "!", colour: "#fbbf24" },
  real_deal: { label: "Real saving", icon: "✓", colour: "#34d399" },
  going_rate: { label: "Normal price", icon: "=", colour: "#60a5fa" },
  above_market: { label: "Cheaper elsewhere", icon: "↑", colour: "#f87171" },
  unverified: { label: "Not enough data", icon: "?", colour: "#a1a7b6" },
};

const PANEL_CSS = `
:host { all: initial; }
.box {
  position: fixed; top: 96px; right: 20px; width: 320px; z-index: 2147483647;
  background: #12141c; color: #eceef4; border: 1px solid rgba(255,255,255,.14);
  border-radius: 16px; box-shadow: 0 24px 60px rgba(0,0,0,.5);
  font: 14px/1.5 Inter, system-ui, -apple-system, "Segoe UI", sans-serif; overflow: hidden;
}
.head { display: flex; align-items: center; gap: 8px; padding: 12px 14px; border-bottom: 1px solid rgba(255,255,255,.08); }
.mark { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 7px; background: linear-gradient(135deg,#ffb547,#ff7a2e); color: #1a0d05; font-weight: 700; font-size: 12px; }
.name { font-weight: 700; letter-spacing: -.02em; }
.name i { color: #ff7a2e; font-style: normal; }
.x { margin-left: auto; background: none; border: 0; color: #8a8fa0; font-size: 18px; line-height: 1; cursor: pointer; padding: 0 2px; }
.x:hover { color: #eceef4; }
.body { padding: 14px; }
.label { display: inline-flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 700; padding: 4px 10px 4px 5px; border-radius: 999px; }
.label span { display: grid; place-items: center; width: 16px; height: 16px; border-radius: 50%; font-size: 10px; color: #0a0b0f; }
.line { margin: 12px 0 0; font-size: 15px; font-weight: 600; letter-spacing: -.01em; }
.nums { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 14px; }
.num { background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.08); border-radius: 12px; padding: 10px; }
.num b { display: block; font-size: 22px; letter-spacing: -.03em; }
.num small { color: #8a8fa0; font-size: 11px; }
.claim b { color: #ff9b5c; }
.sellers { margin: 14px 0 0; padding: 0; list-style: none; display: grid; gap: 6px; }
.sellers li { display: flex; justify-content: space-between; gap: 10px; font-size: 13px; color: #c3c7d3; }
.sellers b { font-variant-numeric: tabular-nums; }
.foot { display: block; margin-top: 14px; text-align: center; padding: 9px; border-radius: 10px; border: 1px solid rgba(255,255,255,.14); color: #eceef4; text-decoration: none; font-weight: 600; font-size: 13px; }
.foot:hover { border-color: #ff7a2e; color: #ff9b5c; }
.muted { color: #8a8fa0; }
.spin { width: 15px; height: 15px; border-radius: 50%; border: 2px solid rgba(255,255,255,.2); border-top-color: #ff7a2e; display: inline-block; animation: s .8s linear infinite; vertical-align: -2px; margin-right: 8px; }
@keyframes s { to { transform: rotate(360deg); } }
`;

const rupees = (x) => "₹" + Math.round(x).toLocaleString("en-IN");
const pct = (x) => Math.round(x * 100) + "%";

function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") n.className = v;
    else if (k === "style") n.style.cssText = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const c of kids) if (c != null) n.append(c);
  return n;
}

// Only a product page counts. Search and home pages are full of [data-asin]
// carousels, and checking whichever product happens to come first would spend
// searches on something the shopper never looked at.
function findAsin() {
  const fromUrl = ASIN_IN_URL.exec(location.pathname);
  return fromUrl ? fromUrl[1] : null;
}

function mount() {
  document.getElementById("aslideal-root")?.remove();
  const host = el("div", { id: "aslideal-root" });
  const root = host.attachShadow({ mode: "open" });
  root.append(el("style", {}, PANEL_CSS));
  const body = el("div", { class: "body" });
  const box = el("div", { class: "box" },
    el("div", { class: "head" },
      el("div", { class: "mark" }, "₹"),
      el("div", { class: "name" }, "Asli", el("i", {}, "Deal")),
      el("button", { class: "x", title: "Close", onclick: () => host.remove() }, "×")),
    body);
  root.append(box);
  document.body.append(host);
  return body;
}

function showWaiting(body) {
  body.replaceChildren(el("p", { class: "muted", style: "margin:0" }, el("i", { class: "spin" }), "Checking this discount against other Indian stores…"));
}

function showError(body, message, server) {
  body.replaceChildren(
    el("p", { style: "margin:0;font-weight:600" }, "Couldn't check this one"),
    el("p", { class: "muted", style: "margin:8px 0 0;font-size:13px" }, message),
    el("a", { class: "foot", href: server, target: "_blank", rel: "noopener" }, "Open AsliDeal"));
}

function showVerdict(body, data, server) {
  const v = data.verdict;
  const kind = KINDS[v.kind] || KINDS.unverified;
  const others = data.offers.filter((o) => !/^amazon/i.test(o.seller)).slice(0, 3);
  const real = v.real_discount;

  body.replaceChildren(
    el("div", { class: "label", style: `color:${kind.colour};background:${kind.colour}1f;border:1px solid ${kind.colour}4d` },
      el("span", { style: `background:${kind.colour}` }, kind.icon), kind.label),
    el("p", { class: "line" }, v.headline),
    el("div", { class: "nums" },
      el("div", { class: "num claim" }, el("b", {}, v.claimed_discount ? pct(v.claimed_discount) : "-"), el("small", {}, "Amazon's \"% off\"")),
      el("div", { class: "num" },
        el("b", { style: real != null && real < 0 ? "color:#f87171" : "color:#34e0a1" },
          real == null ? "?" : real >= 0 ? pct(real) : "+" + pct(-real)),
        el("small", {}, real == null ? "too few sellers" : real >= 0 ? "vs other stores" : "more than others"))),
    others.length
      ? el("ul", { class: "sellers" }, ...others.map((o) =>
          el("li", {}, el("span", {}, o.seller + (o.in_stock ? "" : " (out of stock)")), el("b", {}, rupees(o.price)))))
      : null,
    el("a", { class: "foot", href: `${server}/#check/${data.listing.asin}`, target: "_blank", rel: "noopener" }, "See the full evidence →"));
}

function run() {
  const asin = findAsin();
  if (!asin) return;
  const body = mount();
  showWaiting(body);
  chrome.runtime.sendMessage({ type: "check", asin }, (reply) => {
    if (chrome.runtime.lastError || !reply) {
      return showError(body, chrome.runtime.lastError?.message || "The extension couldn't reach its background worker.", "http://localhost:8000");
    }
    if (!reply.ok) return showError(body, reply.error, reply.server);
    // A dead listing comes back without a verdict, with live listings to try instead.
    if (reply.data.unavailable || !reply.data.verdict) {
      const n = (reply.data.suggestions || []).length;
      return showError(body, (reply.data.error || "No verdict for this listing.") +
        (n ? ` AsliDeal found ${n} live listing${n === 1 ? "" : "s"} of the same product.` : ""), reply.server);
    }
    showVerdict(body, reply.data, reply.server);
  });
}

run();

// Amazon swaps products in without a page load, so follow the URL.
let seen = location.href;
setInterval(() => {
  if (location.href !== seen) {
    seen = location.href;
    run();
  }
}, 1200);
