"""Design review: screenshot the simulator screens and check layout rules.

Usage (server running):  python tools/ui_review.py STAGE [screen ...] [--base http://localhost:8080]
Screens: landing teams team trade trade3 trade4 select picked results (default: all).
"picked" is Choose trades after ticking up to two ideas.

For each screen it saves full-page PNGs at 390x844 (2x) and 1280x800 to design-review/stage-N/,
then checks, at 320 / 390 / 768 / 1280 wide:
  - no horizontal overflow (scrollWidth <= innerWidth)
  - visible buttons, links styled as controls, tabs, checkboxes and tappable rows >= 44px tall
  - text at least 11px (team badge codes excepted)
  - text contrast >= 4.5:1 (3:1 for large text), twice: against the CSS background colors, and
    against the real pixels behind the text (text hidden, page screenshotted), which catches glows
  - numbers use Inter with tabular figures, and digits all have the same width
  - no duplicate element IDs
"""
import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

TEAM = "CHI"  # East team with 4 trade ideas (BKN has 2, SAC none)
SHOT_SIZES = {"phone": (390, 844, 2), "laptop": (1280, 800, 1)}
CHECK_WIDTHS = [320, 390, 768, 1024, 1280]

CHECKS_JS = r"""
() => {
  const out = { overflow: null, small: [], contrast: [], dupIds: [], numbers: [], texts: [] };
  const de = document.documentElement;
  out.overflow = de.scrollWidth > window.innerWidth ? { scrollWidth: de.scrollWidth, innerWidth: window.innerWidth } : null;
  // Boxes that scroll sideways inside the page (e.g. a wide table) count as overflow too.
  out.innerScroll = [];
  document.querySelectorAll("body *").forEach((el) => {
    const ox = getComputedStyle(el).overflowX;
    if ((ox === "auto" || ox === "scroll") && el.scrollWidth > el.clientWidth + 1)
      out.innerScroll.push(`${el.tagName.toLowerCase()}.${el.className} ${el.scrollWidth}>${el.clientWidth}`);
  });

  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    // checkVisibility() also catches content inside a closed <details>, which still reports a box
    const shown = el.checkVisibility ? el.checkVisibility({ visibilityProperty: true }) : true;
    return shown && r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  };
  const name = (el) => (el.getAttribute("aria-label") || el.textContent || el.value || el.tagName).trim().replace(/\s+/g, " ").slice(0, 50);
  const sel = (el) => el.tagName.toLowerCase() + (el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).join(".") : "");

  // Tap targets. A checkbox inside a <label> is measured by its label (the label is the target).
  const targets = new Set();
  document.querySelectorAll("button, a.button, a.back, a.team-card, [role=tab], summary, select, input:not([type=hidden]), label.pick-card, .saved a").forEach((el) => {
    if (el.matches("input[type=checkbox], input[type=radio]") && el.closest("label")) targets.add(el.closest("label"));
    else targets.add(el);
  });
  targets.forEach((el) => {
    if (!visible(el)) return;
    const h = el.getBoundingClientRect().height;
    if (h < 44) out.small.push({ el: sel(el), text: name(el), height: Math.round(h * 10) / 10 });
  });

  // Contrast of every visible text run.
  const parse = (c) => {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const blend = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a), g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a), a: 1,
  });
  const lum = (c) => {
    const f = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  // Only ancestors whose box actually sits behind the text count (labels positioned outside
  // their parent, like the payroll bar markers, don't sit on the parent's fill).
  const background = (el) => {
    const layers = [];
    const er = el.getBoundingClientRect(), cx = er.left + er.width / 2, cy = er.top + er.height / 2;
    for (let n = el; n; n = n.parentElement) {
      const nr = n.getBoundingClientRect();
      if (n !== document.body && n !== document.documentElement && (cx < nr.left || cx > nr.right || cy < nr.top || cy > nr.bottom)) continue;
      const bg = parse(getComputedStyle(n).backgroundColor);
      if (bg && bg.a > 0) { layers.push(bg); if (bg.a >= 1) break; }
    }
    let c = { r: 10, g: 10, b: 10, a: 1 };
    if (layers.length && layers[layers.length - 1].a >= 1) c = layers.pop();
    for (let i = layers.length - 1; i >= 0; i--) c = blend(layers[i], c);
    return c;
  };
  const opacity = (el) => { let o = 1; for (let n = el; n; n = n.parentElement) o *= Number(getComputedStyle(n).opacity); return o; };
  const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const t = walker.currentNode;
    if (!t.textContent.trim()) continue;
    const el = t.parentElement;
    // aria-hidden text (team badges, chart tags) is still seen, so it's checked for contrast too
    if (!el || !visible(el) || el.closest("[hidden]")) continue;
    const s = getComputedStyle(el);
    const isSvg = el instanceof SVGElement;
    const fg = parse(isSvg ? s.fill : s.color);
    if (!fg) continue;
    fg.a *= opacity(el);
    const bg = background(el);
    const r = ratio(blend(fg, bg), bg);
    let size = parseFloat(s.fontSize);
    const weight = Number(s.fontWeight) || 400;
    if (isSvg && el.ownerSVGElement && el.ownerSVGElement.viewBox.baseVal.width) {   // SVG text scales with the chart
      const svgEl = el.ownerSVGElement;
      size *= svgEl.getBoundingClientRect().width / svgEl.viewBox.baseVal.width;
    }
    // Text below 11px (the Impeccable floor), except decorative badge codes that repeat a name beside them.
    if (size < 10.95 && !el.closest(".badge") && !seen.has("size|" + sel(el))) {
      seen.add("size|" + sel(el));
      out.small.push({ el: sel(el), text: "text " + t.textContent.trim().slice(0, 30), height: Math.round(size * 10) / 10 });
    }
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = large ? 3 : 4.5;
    const rr = el.getBoundingClientRect();
    // Text in the fixed bottom bar sits on a solid fill; the CSS check above covers it.
    if (out.texts.length < 800 && !el.closest(".action-bar, .data-warning")) out.texts.push({
      el: sel(el), text: t.textContent.trim().slice(0, 40), need, fg: { r: fg.r, g: fg.g, b: fg.b, a: fg.a },
      x: rr.left + scrollX, y: rr.top + scrollY, w: rr.width, h: rr.height,
    });
    const key = sel(el) + "|" + s.color + "|" + bg.r + bg.g + bg.b;
    if (r < need && !seen.has(key)) {
      seen.add(key);
      out.contrast.push({ el: sel(el), text: t.textContent.trim().slice(0, 40), ratio: Math.round(r * 100) / 100, need });
    }
  }

  // Numbers: Inter + tabular figures, and every digit the same width in that font.
  const NUMBER_SEL = ".big-number, .stat .value, .payroll-figures .amount, .suggestion-head .gain, .range-pill strong, " +
    ".combined-card .combined strong, .standings td, .data-table td, .amt, .num, .gauge-value, .chart .tag";
  const probe = document.createElement("span");
  probe.style.cssText = "position:absolute;visibility:hidden;white-space:nowrap";
  document.body.appendChild(probe);
  const seenNum = new Set();
  document.querySelectorAll(NUMBER_SEL).forEach((el) => {
    if (!visible(el)) return;
    const s = getComputedStyle(el);
    const key = sel(el);
    if (seenNum.has(key)) return;
    seenNum.add(key);
    const family = s.fontFamily.split(",")[0].replace(/["']/g, "").trim();
    const tab = /tabular-nums/.test(s.fontVariantNumeric);
    probe.style.font = s.font; probe.style.fontVariantNumeric = s.fontVariantNumeric; probe.style.letterSpacing = s.letterSpacing;
    const widths = ["26.0 → 33.7", "11.1 → 88.8", "00.0 → 44.4"].map((txt) => { probe.textContent = txt; return probe.getBoundingClientRect().width; });
    const shift = Math.max(...widths) - Math.min(...widths);
    if (family !== "Inter" || !tab || shift > 0.5)
      out.numbers.push(`${key} '${el.textContent.trim().slice(0, 20)}' font=${family} tabular=${tab} width shift=${shift.toFixed(1)}px`);
  });
  probe.remove();

  const ids = {};
  document.querySelectorAll("[id]").forEach((el) => { ids[el.id] = (ids[el.id] || 0) + 1; });
  out.dupIds = Object.entries(ids).filter(([, n]) => n > 1).map(([id, n]) => `${id} x${n}`);
  return out;
}
"""


HIDE_TEXT = """*, *::before, *::after { color: transparent !important; -webkit-text-fill-color: transparent !important;
  text-shadow: none !important; caret-color: transparent !important; }
svg text { fill: transparent !important; }
.action-bar, .data-warning { visibility: hidden !important; }"""

PIXEL_JS = r"""
async ({ png, texts }) => {
  const img = new Image();
  img.src = "data:image/png;base64," + png;
  await img.decode();
  const c = document.createElement("canvas");
  c.width = img.width; c.height = img.height;
  const g = c.getContext("2d", { willReadFrequently: true });
  g.drawImage(img, 0, 0);
  const k = img.width / document.documentElement.scrollWidth;
  const lin = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = (r, gg, b) => 0.2126 * lin(r) + 0.7152 * lin(gg) + 0.0722 * lin(b);
  const out = [], seen = new Set();
  for (const t of texts) {
    // sample slightly inside the box so a cell's or chip's own border isn't read as background
    const ix = Math.min(4, t.w * 0.2), iy = Math.min(2, t.h * 0.2);
    const x = Math.max(0, Math.floor((t.x + ix) * k)), y = Math.max(0, Math.floor((t.y + iy) * k));
    const w = Math.min(c.width - x, Math.ceil((t.w - 2 * ix) * k)), h = Math.min(c.height - y, Math.ceil((t.h - 2 * iy) * k));
    if (w < 1 || h < 1) continue;
    const d = g.getImageData(x, y, w, h).data;
    const step = Math.max(1, Math.floor((w * h) / 4000));
    const ls = [], px = [];
    for (let i = 0; i < d.length; i += 4 * step) { ls.push(lum(d[i], d[i + 1], d[i + 2])); px.push([d[i], d[i + 1], d[i + 2]]); }
    const order = ls.map((v, i) => i).sort((a, b) => ls[a] - ls[b]);
    const median = ls[order[Math.floor(order.length / 2)]];
    // the text's painted color over the median background
    const m = px[order[Math.floor(order.length / 2)]];
    const fg = [0, 1, 2].map((j) => [t.fg.r, t.fg.g, t.fg.b][j] * t.fg.a + m[j] * (1 - t.fg.a));
    const lf = lum(...fg);
    // worst case: light text vs the 90th-percentile brightest background pixel (dark text: 10th)
    const pick = lf > median ? order[Math.floor(order.length * 0.9)] : order[Math.floor(order.length * 0.1)];
    const lb = ls[pick];
    const ratio = (Math.max(lf, lb) + 0.05) / (Math.min(lf, lb) + 0.05);
    const key = t.el + "|" + Math.round(ratio * 10);
    if (ratio < t.need && !seen.has(key)) { seen.add(key); out.push({ el: t.el, text: t.text, ratio: Math.round(ratio * 100) / 100, need: t.need }); }
  }
  return out;
}
"""


def pixel_contrast(page, texts):
    """Contrast against the real pixels behind each text run (counts gradients and glows)."""
    import base64
    style = page.add_style_tag(content=HIDE_TEXT)
    page.wait_for_timeout(50)
    png = base64.b64encode(page.screenshot(full_page=True)).decode()
    style.evaluate("el => el.remove()")
    return page.evaluate(PIXEL_JS, {"png": png, "texts": texts})


def settle(page):
    """Wait until loading text, skeletons and 'Updating…' are gone."""
    page.wait_for_load_state("networkidle")
    page.wait_for_function(
        """() => !document.querySelector('.loading, .searching, .skeleton')
              && !/Updating…/.test(document.body.innerText)""",
        timeout=120_000,
    )
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(300)


def open_screen(page, base, screen, state):
    """Go to a screen. `state` carries links found on earlier screens (trade, results)."""
    if screen == "landing":
        page.goto(f"{base}/#/")
    elif screen == "teams":
        page.goto(f"{base}/#/teams")
    elif screen == "team":
        page.goto(f"{base}/#/team/{TEAM}")
    elif screen in ("trade", "trade3", "trade4"):
        if "trade" not in state:
            page.goto(f"{base}/#/team/{TEAM}")
            settle(page)
            state["trade"] = page.eval_on_selector(f'a[href^="#/trade/{TEAM}/"]', "a => a.getAttribute('href')")
        href = state["trade"]
        if screen != "trade":  # same trade with extra (empty) teams: tests the 3- and 4-team layouts
            path, query = href.split("?", 1)
            extra = ["LAL", "BOS"][: int(screen[-1]) - 2]
            href = "/".join([path] + extra) + "?" + query
        page.goto(f"{base}/{href}")
    elif screen == "select":
        page.goto(f"{base}/#/select/{TEAM}")
    elif screen in ("picked", "results"):
        page.goto(f"{base}/#/select/{TEAM}")
        settle(page)
        if not page.locator("input[data-pick]:checked").count():  # picks live in page memory
            for _ in range(2):  # pick up to two ideas, one at a time
                box = page.locator("input[data-pick]:not(:checked)")
                if not box.count():
                    break
                # click, not check(): the screen redraws on change, replacing the box
                box.first.click()
                page.wait_for_timeout(300)
                settle(page)
            state["results"] = page.eval_on_selector(".action-bar a.button", "a => a.getAttribute('href')")
        if screen == "results":
            page.goto(f"{base}/{state['results']}")
    settle(page)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage")
    ap.add_argument("screens", nargs="*", default=["landing", "teams", "team", "trade", "trade3", "trade4", "select", "picked", "results"])
    ap.add_argument("--base", default="http://localhost:8080")
    args = ap.parse_args()
    out_dir = Path("design-review") / f"stage-{args.stage}"
    out_dir.mkdir(parents=True, exist_ok=True)

    report, state = {}, {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        # One context keeps the in-memory picks between the select and results screens.
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                  reduced_motion="reduce")
        page = ctx.new_page()
        for screen in args.screens:
            report[screen] = {}
            for label, (w, h, dpr) in SHOT_SIZES.items():
                shot_ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr,
                                               reduced_motion="reduce")
                p = shot_ctx.new_page()
                open_screen(p, args.base, screen, state)
                p.screenshot(path=str(out_dir / f"{screen}-{label}.png"), full_page=True)
                if p.locator(".action-bar").count():
                    # Full-page shots draw the fixed CTA mid-page; this one shows it over the page end.
                    p.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                    p.wait_for_timeout(200)
                    p.screenshot(path=str(out_dir / f"{screen}-{label}-bottom.png"))
                shot_ctx.close()
            open_screen(page, args.base, screen, state)
            for w in CHECK_WIDTHS:
                page.set_viewport_size({"width": w, "height": 844})
                page.wait_for_timeout(150)
                r = page.evaluate(CHECKS_JS)
                r["pixelContrast"] = pixel_contrast(page, r.pop("texts"))
                report[screen][w] = r
        browser.close()

    (out_dir / "report.json").write_text(json.dumps(report, indent=2))
    failures = 0
    for screen, widths in report.items():
        for w, r in widths.items():
            lines = []
            if r["overflow"]:
                lines.append(f"  overflow: {r['overflow']}")
            for x in r.get("innerScroll", []):
                lines.append(f"  scrolls sideways: {x}")
            for s in r["small"]:
                lines.append(f"  <44px: {s['el']} '{s['text']}' {s['height']}px")
            for c in r["contrast"]:
                lines.append(f"  contrast {c['ratio']} < {c['need']}: {c['el']} '{c['text']}'")
            for c in r.get("pixelContrast", []):
                lines.append(f"  pixel contrast {c['ratio']} < {c['need']}: {c['el']} '{c['text']}'")
            for n in r.get("numbers", []):
                lines.append(f"  number font: {n}")
            for d in r["dupIds"]:
                lines.append(f"  duplicate id: {d}")
            if lines:
                failures += len(lines)
                print(f"{screen} @ {w}px")
                print("\n".join(lines))
    print(f"\n{failures} issue(s). Screenshots and report.json in {out_dir}/")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
