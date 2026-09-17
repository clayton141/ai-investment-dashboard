window.SUPABASE_URL = "https://rrxfqwfnubipbmoyoewj.supabase.co";
window.SUPABASE_ANON_KEY = "sb_publishable_U3IJ6XyOVGH7icn9Xt0Njg_mnJURgPz";

// Premarket UI enhancement. data.json is refreshed by GitHub Actions during US premarket.
(function () {
  let preMap = {};
  let preStatus = "";
  let preUpdatedAt = "";

  const money = n => n == null ? "—" : "$" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  const pct2 = n => n == null ? "—" : (Number(n) > 0 ? "+" : "") + Number(n).toFixed(2) + "%";

  function decorate(selector) {
    document.querySelectorAll(selector + " .card").forEach(card => {
      const tickerEl = card.querySelector(".ticker");
      if (!tickerEl) return;
      const ticker = tickerEl.textContent.trim().split(/\s+/)[0];
      const s = preMap[ticker];
      let box = card.querySelector(".premarket-live");

      if (preStatus === "PRE" && s && s.preMarketState === "PRE" && s.preMarketPrice != null) {
        if (!box) {
          box = document.createElement("div");
          box.className = "premarket-live";
          const firstRow = card.querySelector(".row");
          if (firstRow) card.insertBefore(box, firstRow); else card.appendChild(box);
        }
        const cls = Number(s.preMarketPct) >= 0 ? "pos" : "neg";
        box.innerHTML = `<div class="row"><span class="muted"><span class="pill">PRE</span> 盤前</span><b>${money(s.preMarketPrice)} <span class="${cls}">${pct2(s.preMarketPct)}</span></b></div><div class="small muted" style="text-align:right;margin-top:3px">${s.preMarketAsOf || ""}</div>`;
      } else if (box) {
        box.remove();
      }
    });
  }

  function renderPremarket() {
    decorate("#cards");
    decorate("#holdings");
    const header = document.getElementById("marketAsOf");
    if (header) {
      const base = header.textContent.replace(/\s·\sPremarket:.*$/, "");
      header.textContent = (preStatus === "PRE" && preUpdatedAt) ? `${base} · Premarket: ${preUpdatedAt}` : base;
    }
  }

  async function loadPremarket() {
    try {
      const r = await fetch("./data.json?pm=" + Date.now(), { cache: "no-store", headers: { "Cache-Control": "no-cache" } });
      if (!r.ok) return;
      const d = await r.json();
      preMap = Object.fromEntries((d.watchlist || []).map(s => [s.ticker, s]));
      preStatus = d.preMarketStatus || "";
      preUpdatedAt = d.preMarketUpdatedAt || "";
      renderPremarket();
    } catch (_) {}
  }

  window.addEventListener("DOMContentLoaded", () => {
    const observer = new MutationObserver(() => renderPremarket());
    observer.observe(document.body, { childList: true, subtree: true });
    loadPremarket();
    setInterval(loadPremarket, 5 * 60 * 1000);
  });
})();
