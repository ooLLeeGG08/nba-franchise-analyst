"""Design review: screenshot the simulator screens and check layout rules.

Usage (server running):  python tools/ui_review.py STAGE [screen ...] [--base http://localhost:8080]
Screens: landing teams team trade trade3 trade4 select picked results (default: all).
"picked" is Choose trades after ticking up to two ideas.

For each screen it saves full-page PNGs at 390x844 (2x) and 1280x800 to design-review/stage-N/,
then checks, at 320 / 390 / 768 / 1280 wide:
  - no horizontal overflow (scrollWidth <= innerWidth)
  - visible buttons, links styled as controls, tabs, checkboxes and tappable rows >= 44px tall
  - text contrast >= 4.5:1 (3:1 for large text) against the painted background
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
  const out = { overflow: null, small: [], contrast: [], dupIds: [] };
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
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
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
    if (!el || !visible(el) || el.closest("[hidden], [aria-hidden=true]:not(svg)")) continue;
    const s = getComputedStyle(el);
    const isSvg = el instanceof SVGElement;
    const fg = parse(isSvg ? s.fill : s.color);
    if (!fg) continue;
    fg.a *= opacity(el);
    const bg = background(el);
    const r = ratio(blend(fg, bg), bg);
    const size = parseFloat(s.fontSize), weight = Number(s.fontWeight) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = large ? 3 : 4.5;
    const key = sel(el) + "|" + s.color + "|" + bg.r + bg.g + bg.b;
    if (r < need && !seen.has(key)) {
      seen.add(key);
      out.contrast.push({ el: sel(el), text: t.textContent.trim().slice(0, 40), ratio: Math.round(r * 100) / 100, need });
    }
  }

  const ids = {};
  document.querySelectorAll("[id]").forEach((el) => { ids[el.id] = (ids[el.id] || 0) + 1; });
  out.dupIds = Object.entries(ids).filter(([, n]) => n > 1).map(([id, n]) => `${id} x${n}`);
  return out;
}
"""


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
                report[screen][w] = page.evaluate(CHECKS_JS)
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
