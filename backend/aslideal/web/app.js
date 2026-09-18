// Seller titles and names come from third-party listings, so all text goes in through
// textContent (via el()), never innerHTML.

const $ = (id) => document.getElementById(id);

const LABELS = {
  reference_gap: "Discount from a price nobody charges",
  real_deal: "Real saving",
  going_rate: "Normal price",
  above_market: "Cheaper elsewhere",
  unverified: "Not enough data",
};

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "style") node.style.cssText = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c != null) node.append(c);
  return node;
}

function rupees(x) {
  return "₹" + Math.round(x).toLocaleString("en-IN");
}

function pct(x) {
  return Math.round(x * 100) + "%";
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

async function loadStatus() {
  try {
    const s = await api("/api/status");
    const mode = $("mode");
    mode.hidden = false;
    if (s.demo) {
      mode.textContent = "Demo: recorded data";
      mode.title = "No SerpApi key set, so only the recorded products below can be checked.";
    } else {
      mode.textContent = s.quota ? `Live · ${s.quota.left} searches left` : "Live";
      mode.classList.add("live");
    }
    if (s.samples.length) {
      $("samples").hidden = false;
      const list = $("sample-list");
      list.replaceChildren(...s.samples.map((p) =>
        el("button", { class: "sample", type: "button", title: p.title, onclick: () => runCheck(p.asin) },
          shortName(p.title))));
    }
  } catch {
    /* the page works without the status line */
  }
}

function shortName(title) {
  return title.split(/[,|(:]/)[0].split(" ").slice(0, 5).join(" ");
}

async function onSubmit(e) {
  e.preventDefault();
  const q = $("q").value.trim();
  if (!q) return;
  busy(true);
  $("results").hidden = true;
  $("report").hidden = true;
  show("");
  try {
    const r = await api("/api/search?q=" + encodeURIComponent(q));
    if (r.asin) return await runCheck(r.asin, false);
    renderResults(r.results);
  } catch (err) {
    show(err.message, true);
  } finally {
    busy(false);
  }
}

function renderResults(items) {
  const withMrp = items.filter((i) => !i.sponsored);
  if (!withMrp.length) return show("Amazon.in returned nothing for that. Try the model name, or paste the product link.", true);
  $("results").hidden = false;
  $("result-list").replaceChildren(...withMrp.slice(0, 10).map((i) =>
    el("li", {},
      el("button", { class: "result", type: "button", onclick: () => runCheck(i.asin) },
        i.thumbnail ? el("img", { src: i.thumbnail, alt: "" }) : el("span"),
        el("span", { class: "t" }, i.title),
        el("span", { class: "p" },
          el("b", {}, rupees(i.price)),
          i.mrp ? el("div", {}, el("span", { class: "strike" }, rupees(i.mrp)), " ", el("span", { class: "off" }, pct(i.claimed_discount) + " off")) : null)))));
}

async function runCheck(asin, manageBusy = true) {
  if (manageBusy) busy(true);
  $("results").hidden = true;
  $("report").hidden = true;
  show("Checking Amazon.in, Google Shopping and Google search… a live check takes about half a minute.");
  try {
    const r = await api("/api/check/" + encodeURIComponent(asin));
    show("");
    renderReport(r);
  } catch (err) {
    show(err.message, true);
  } finally {
    if (manageBusy) busy(false);
  }
}

function busy(on) {
  const b = $("form").querySelector("button");
  b.disabled = on;
  b.textContent = on ? "Checking…" : "Check";
}

function renderReport(r) {
  const v = r.verdict;
  const L = r.listing;
  const card = $("verdict");
  card.className = "verdict k-" + v.kind;
  $("v-label").textContent = LABELS[v.kind] || v.kind;
  $("v-title").textContent = L.title;
  $("v-link").href = L.link;
  const thumb = $("v-thumb");
  thumb.hidden = !L.thumbnail;
  if (L.thumbnail) thumb.src = L.thumbnail;
  $("v-headline").textContent = v.headline;

  renderBars(v);
  renderStrip(v, r.offers);
  $("v-notes").replaceChildren(...v.notes.map((n) => el("li", {}, n)));

  $("seller-rows").replaceChildren(...r.offers.map((o) => {
    const own = /^amazon/i.test(o.seller);
    return el("tr", { class: own ? "own" : "" },
      el("td", {}, o.seller + (own ? " (the listing being checked)" : "")),
      el("td", { class: "num" }, rupees(o.price)),
      el("td", { class: o.in_stock ? "" : "oos" }, o.in_stock ? "In stock" : "Out of stock"),
      el("td", { class: "ttl" }, link(o)));
  }));
  if (!r.offers.length) {
    $("seller-rows").replaceChildren(el("tr", {}, el("td", { colspan: "4", class: "muted" }, "No matching listings found.")));
  }

  const rej = r.rejected;
  $("rejected-box").hidden = !rej.length;
  $("rejected-sum").textContent = `${rej.length} listing${rej.length === 1 ? "" : "s"} left out as evidence`;
  $("rejected-rows").replaceChildren(...rej.map((o) =>
    el("tr", {},
      el("td", {}, o.seller),
      el("td", { class: "num" }, rupees(o.price)),
      el("td", {}, o.reason),
      el("td", { class: "ttl" }, link(o)))));

  $("report").hidden = false;
  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

function link(o) {
  if (!/^https?:\/\//.test(o.link || "")) return o.title;
  return el("a", { href: o.link, target: "_blank", rel: "noopener nofollow", title: o.title }, o.title);
}

function renderBars(v) {
  const rows = [];
  if (v.mrp && v.claimed_discount > 0) {
    rows.push(bar("Amazon's \"% off\"", v.claimed_discount, "var(--accent)", pct(v.claimed_discount)));
  }
  if (v.street_price) {
    const real = v.real_discount;
    rows.push(real >= 0
      ? bar("Saving vs other stores", real, "var(--deal)", pct(real))
      : bar("Extra vs other stores", -real, "var(--over)", "+" + pct(-real)));
  }
  $("bars").replaceChildren(...rows);
}

function bar(label, frac, color, text) {
  return el("div", { class: "bar-row" },
    el("span", {}, label),
    el("div", { class: "bar-track" }, el("div", { class: "bar-fill", style: `width:${Math.min(frac, 1) * 100}%;background:${color}` })),
    el("b", {}, text));
}

// A number line from the cheapest seller to the M.R.P.: every seller is a dot,
// with Amazon's price, the street price and the M.R.P. labelled.
function renderStrip(v, offers) {
  const strip = $("strip");
  const prices = offers.filter((o) => o.in_stock).map((o) => o.price).concat([v.price]);
  if (v.street_price) prices.push(v.street_price);
  if (v.mrp) prices.push(v.mrp);
  if (prices.length < 3) { strip.hidden = true; return; }
  let lo = Math.min(...prices), hi = Math.max(...prices);
  const pad = (hi - lo) * 0.06 || hi * 0.05;
  lo -= pad; hi += pad;
  const frac = (p) => (p - lo) / (hi - lo);
  const x = (p) => frac(p) * 100 + "%";
  // Labels near either end hang inwards so they don't run off a narrow screen.
  const side = (p) => (frac(p) < 0.2 ? " left" : frac(p) > 0.8 ? " right" : "");

  const marks = [el("div", { class: "axis" })];
  for (const o of offers) {
    if (!o.in_stock || /^amazon/i.test(o.seller)) continue;
    marks.push(el("div", { class: "mark", style: `left:${x(o.price)}`, title: `${o.seller} ${rupees(o.price)}` },
      el("div", { class: "dot seller" })));
  }
  const named = (price, cls, caption, dir) =>
    el("div", { class: `mark ${dir}${side(price)}`, style: `left:${x(price)}` },
      el("div", { class: "dot " + cls }), el("span", { class: "cap" }, caption));
  if (v.street_price) marks.push(named(v.street_price, "street", "Other stores " + rupees(v.street_price), "down"));
  marks.push(named(v.price, "amazon", "Amazon " + rupees(v.price), "up"));
  if (v.mrp) marks.push(named(v.mrp, "mrp", "M.R.P. " + rupees(v.mrp), "up"));
  strip.replaceChildren(...marks);
  strip.hidden = false;
}

$("form").addEventListener("submit", onSubmit);
loadStatus();
