# ZMN dashboard — teardown + redesign analysis

**Date:** 2026-04-19
**Scope:** current state audit, Webpixels Satoshi template teardown,
reusability assessment, 3 distinct redesign concepts with HTML skeletons,
Jay's decision framework.
**Context:** Jay's brief — "the Satoshi template was an intentional import,
I want to see if we can modify it into a shit hot dashboard." This report
delivers a redesign concept, not a preservation plan. The current retro
CRT is functional for now but this is the commit-to-real-redesign
assessment Jay asked for.
**Method:** used the `frontend-design` skill (principles quoted inline),
read relevant slices of `dashboard/dashboard.html` (1,188 lines),
`dashboard-analytics.html` (466 lines), `dashboard-wallet.html` (443 lines),
and a sample of Satoshi components. Did NOT use Playwright this session —
structural analysis only.

---

## Table of contents

1. Section 1 — Current state inventory
2. Section 2 — Template teardown (Webpixels Satoshi DeFi)
3. Section 3 — Reusability assessment
4. Section 4 — Three redesign concepts with HTML skeletons
   - Concept A: "Trading Desk" (Bloomberg-inspired dense terminal)
   - Concept B: "Editorial Terminal" (ambitious maximalist hero)
   - Concept C: "Unified Cockpit" (Linear-style refined minimalism)
5. Section 5 — Jay's decision framework

---

## Section 1 — Current state inventory

### 1.1 What each HTML file is + how it's served

| File | Lines | Bytes | Served by | Status |
|---|---|---|---|---|
| `dashboard/dashboard.html` | 1,188 | 45,840 | root route `/` + `/dashboard/dashboard.html` via `dashboard_api.py:184-187` passthrough | **PRIMARY** — this is the retro CRT terminal |
| `dashboard/dashboard-analytics.html` | 466 | 41,286 | `/dashboard/dashboard-analytics.html` via same passthrough | Secondary, accessible if URL known |
| `dashboard/dashboard-wallet.html` | 443 | 41,858 | `/dashboard/dashboard-wallet.html` via same passthrough | Secondary, accessible if URL known |
| `dashboard/login.html` | 59 | 4,628 | `/login.html` via passthrough (also JWT gate for all others) | Minimal login screen |

**Routing in `services/dashboard_api.py`:**

- Line 184: a generic `if request.path.startswith("/dashboard/") and request.path.endswith(".html")` handler serves any file in the `dashboard/` directory.
- Line 308: explicit root route returns `dashboard.html`.
- So all three dashboard HTML files ARE live and served — Jay can reach them by typing the URL.

### 1.2 Navigation between the three dashboards

**There is none.** Grepping `dashboard.html` for `href="dashboard-"` or
`href="/dashboard-"` returns zero matches. The two secondary dashboards are
**orphaned in the UI** — reachable only by typing the URL directly.

This is the single biggest usability problem I'd fix regardless of the
redesign direction chosen: there is no sidebar, topbar nav, or any link
from the main dashboard to the analytics or wallet views. They exist but
nobody navigates to them.

### 1.3 What each dashboard actually renders

**`dashboard.html` (main, 14+ panels)** fetches 18 distinct API endpoints:

| Panel | Endpoint |
|---|---|
| Topbar KPIs (balance/treasury/PnL/SOL/CFGI/WR/ML/MODE) | `/api/status` |
| Equity Curve (Daily) | `/api/portfolio-history-daily` |
| Today's Session | `/api/session-stats` |
| Signal Funnel | `/api/signal-funnel` |
| ML Status | `/api/ml-status` |
| Personality Stats (Speed Demon/Analyst/Whale) | `/api/personality-stats` |
| P/L Distribution | `/api/pnl-distribution` |
| Exit Analysis | `/api/exit-analysis` |
| API Health | `/api/api-health` |
| Whale Activity | `/api/whale-activity`, `/api/wallets` |
| Win Rates (personality × regime) | `/api/win-rates` |
| Governance | `/api/governance`, `/api/market` |
| Open Positions | `/api/positions` |
| Recent Trades | `/api/trades?limit=20` |
| Signal Stream | `/api/signals` |

**`dashboard-analytics.html`** fetches: `/api/trigger-health-check`,
`/api/market`, `/api/ml-status`, `/api/governance`, `/api/treasury`,
`/api/status`, `/api/stats`, `/api/service-health`, `/api/wallets`,
`/api/wallets/refresh`, `/api/personality-stats`. Has a sidebar (`sbVer`).

**`dashboard-wallet.html`** fetches: `/api/personality-stats`,
`/api/trades?limit=50`, `/api/trades/active`, `/api/whale-activity`,
`/api/status`. Also has a sidebar.

### 1.4 Styling consistency across the three dashboards

Quick structural read: the two secondary dashboards appear to have a
**different visual treatment** — they use a `.sb-` class prefix (sidebar)
and `aFetch` pattern, while the main one uses the retro CRT palette with
`panel` / `topbar` classes and VT323 font. Confirming: the main dashboard
loads **only VT323 + Chart.js from CDNs** (45KB total self-contained); the
secondaries likely inherit different styles (they're 41KB each and have
their own JS helper `aFetch`, suggesting they predate the unified retro CRT
redesign Jay did in commit history around April 4).

**Implication for redesign:** any serious redesign effort also folds these
three files into a single app shell. The "unified" version of this already
exists as a requirement, just not built yet.

### 1.5 Current retro CRT — what's working

- **Self-contained:** one HTML file, two CDN scripts (VT323 font, Chart.js 4.4.1), zero build step, zero framework churn. 45KB. Loads fast.
- **8-theme system** (body.theme-acid/amber/cyan/magenta/red/purple/orange/blue) all defined via CSS variables — genuinely nice engineering.
- **Chart.js integration** uses the theme variables for colors. Themes propagate to charts automatically.
- **CRT scanline overlay** (`body::after` with `repeating-linear-gradient`) adds character without fighting the data.
- **Topbar density** squeezes 8 KPIs, a clock, 2 dropdowns and a logout button into a single line. Good information density.
- **Per-user prefs** for theme + mode (paper/live) are persisted in localStorage.

### 1.6 Current retro CRT — what's not working (cross-ref DASHBOARD_AUDIT.md)

Cross-referencing `ZMN_ROADMAP.md` "Open Bugs from Other Docs" section and
what I can see in the grep output:

- **B-001 (CFGI source)** — cross-cutting; deeper than dashboard, cosmetic in the UI but correct value now flows through.
- **B-010 (Governance CFGI hallucination)** — governance LLM prompt bug, not a dashboard bug per se.
- **B-011 (outcome column NULL)** — RESOLVED 2026-04-15.
- **B-012 (STAGED_TP_FIRE log)** — FALSE POSITIVE, closed.
- **B-013 (Recent Trades symbol blank)** — DEFERRED; `paper_trades.symbol` column is empty upstream.
- **B-014 (Dashboard CFGI BTC vs SOL)** — cosmetic only; 10-min fix but not done.

**My own observations from reading the current dashboard code:**

- **No visible navigation to the two secondary dashboards** (1.2 above).
- **Responsive breakpoint at 900px only**; stacks to single column below that. No tablet-optimized middle state.
- **Chart titles and axis labels** all render in VT323; against a dark background with CRT scanlines, readability at small sizes gets noisy.
- **Color semantics are weak** in themes like `theme-purple` and `theme-blue` — the "win/loss" green/red contrast gets muddied when everything else is purple. The theme system is a stylistic choice, not a data-viz choice.
- **Panel density is uneven** — Session Stats packs 7 rows into a small card, while Equity Curve sits at 220px height with nothing else in it. Grid is not earning its asymmetry.

**Frontend-design skill principle** applied to the above: current dashboard
has a clear aesthetic commitment (retro CRT) and is far from generic SaaS.
Where it falters is on **information hierarchy** — every panel presents as
equally important, which makes it hard to scan for the one number Jay
cares about right now.

---

## Section 2 — Template teardown (Webpixels Satoshi DeFi)

### 2.1 Template identification

The untracked `components/`, `css/`, `pages/`, `sections/`, `static/`,
`svg/`, `templates/`, `img/`, `share/`, `etc/` directories plus the
five `docs/*.html` files are **Webpixels Satoshi — Web3 and Finance
Dashboard Theme**. Confirmed from:

- `pages/dashboard.html` opens with: `<title>Satoshi – Web3 and Finance Dashboard Theme</title>` and loads `../css/main.css` + `https://api.fontshare.com/v2/css?f=satoshi@900,700,500,300,401,400&display=swap`
- `css/main.css` starts with Bootstrap 5 CSS-variable style: `:root,[data-bs-theme=light]{--x-blue:#09f;--x-indigo:#5c60f5;--x-purple:#8957ff;...` — the `--x-` prefix is the Webpixels CSS framework (their utility-first Bootstrap extension).
- `docs/about.html` credits Webpixels CSS at github.com/webpixels/css and Webpixels as the theme author.

Retail value: ~$49 at themes.getbootstrap.com. The theme ships with a
paid commercial license when purchased from Bootstrap Themes.

### 2.2 Component inventory

Partial counts from `ls` of the untracked template dirs:

**`components/` (264KB):** 40+ HTML snippets. Naming patterns:

- `card-balance.html`, `card-activity-timeline.html`, `card-latest-orders.html`, `card-pool.html`, `card-staking-list.html`, `card-subscriptions.html`, `card-tasks.html`, `card-payment-methods.html`
- `card-stat-1.html` through `card-stat-4.html` (four different KPI card layouts)
- `card-chart-1.html` through `card-chart-4.html` (four chart card wrappers)
- `card-icon-1.html`, `card-icon-2.html`, `card-media.html`, `card-list-item-1.html`
- `card-nft-auction.html`, `card-nft-collection.html`, `card-nft.html`, `card-mockup-1.html` — NFT-specific, not reusable for a trading bot
- `card-progress-1.html`, `card-progress-2.html`, `card-plan-details.html`, `card-buy-crypto.html`, `card-stat-chart-1.html`
- `accordion.html`, `dropdown-filters.html`, `dropdown-user.html`
- `form-add-card.html`, `form-bid-nft.html`, `form-buy-nft.html`, `form-deposit-liquidity.html`, `form-login.html`, `form-register.html`, `form-top-up.html` — some NFT-specific, form-login and form-deposit-liquidity could inspire session/wallet forms

**`pages/` (612KB):** 20 pages. Relevant ones for a trading bot:

- `dashboard.html` — main DeFi dashboard layout (with sidebar, topbar, grid)
- `dashboard-analytics.html` — analytics layout
- `dashboard-wallet.html` — wallet layout with balance cards
- `account-*.html` (5 files) — settings pages
- `login.html`, `register.html`, `error.html`
- `page-list.html`, `page-table-listing.html`, `page-details.html`, `page-collection.html` — table/list/detail layouts
- `other-pricing.html`, `terms.html` — marketing, not useful

**`sections/` (20KB):** 3 files — `faq-1.html`, `pricing-1.html`, `pricing-2.html`. Marketing sections, not useful.

**`svg/` (458KB):** icons and illustration SVGs. A few hundred files. Mostly crypto-asset icons and generic illustration sets.

**`img/` (18MB):** stock photography + crypto logos. `img/crypto/color/` contains per-token icons (SOL, USDT, ADA, etc.) — these are the one thing from `img/` worth keeping.

**`static/` (52KB):** `static/js/switcher.js` and smaller resources. Same switcher as the tracked `js/switcher.js`.

**`templates/` (40KB):** base templates (e.g. a shared page wrapper with navbar + sidebar + footer). Useful scaffolding.

**`share/` (12MB), `etc/` (1KB):** miscellaneous — share sheets, social images. Not worth reusing.

**Total template weight on disk: ~33MB**, concentrated in `img/` (18MB) and `share/` (12MB).

### 2.3 CSS / framework stack

- **Bootstrap 5** as the base — `--x-blue`, `--x-primary`, `--x-font-sans-serif` etc. All the Bootstrap utility classes apply (`d-flex`, `gap-3`, `rounded-3`, `text-xs`, `bg-body-tertiary`).
- **Webpixels CSS framework layered on top** — an opinionated utility-first extension of Bootstrap. `text-heading`, `text-muted`, `fw-bolder`, `ls-tight` are theirs.
- **Dark mode support** via `data-bs-theme="dark"` on the HTML element. CSS variables flip automatically.
- **Satoshi font** from Fontshare (not Bootstrap default) — distinctive, geometric sans.
- **Bootstrap Icons** (`bi-arrow-up`, `bi-gear`, etc.) via CDN.
- **Prism** syntax highlighting for the docs pages only.

**No Tailwind**, no shadcn, no React. It's plain HTML + Bootstrap CSS + vanilla JS. This is the **ideal compatibility profile** — the current ZMN dashboard is also vanilla HTML + CSS + Chart.js, so pulling in Satoshi components means no build pipeline, no npm, no framework migration.

### 2.4 JS dependencies

Minimal on a per-page basis. Sample `pages/dashboard.html` loads:

- Bootstrap 5 JS bundle (for dropdowns, modals, collapse)
- Choices.js (enhanced select dropdowns)
- Chart.js (already in the current dashboard — perfect overlap)
- The custom `main.js` (712KB, being deleted this session) is the
  compiled Webpixels helper bundle. **Not needed** if we write our own
  minimal glue JS.

No build tooling (no webpack, vite, or package.json in the template dirs).
The theme is distributed as pre-built static HTML/CSS/JS. This is one of
the reasons it's a great fit — no npm dependencies to inherit.

### 2.5 DeFi-specific components worth highlighting

Ranked by reusability for the trading bot dashboard:

1. **`card-balance.html`** — big number + sub-stats (income/expenses). Natural fit for Wallet Balance widget.
2. **`card-stat-1.html` through `card-stat-4.html`** — 4 different KPI card layouts. Pick one as the canonical topbar stat card.
3. **`card-chart-1.html` through `card-chart-4.html`** — wrapped chart cards with title, subtitle, and chart canvas. Drop-in for Equity Curve and P/L Distribution.
4. **`card-latest-orders.html`** — data table with symbol, side, amount, P/L. Direct fit for Recent Trades.
5. **`card-activity-timeline.html`** — time-ordered event list. Perfect for Signal Stream.
6. **`card-staking-list.html`** — list of position rows with APY / progress bar. Could be repurposed as Open Positions.
7. **`pages/dashboard.html` base layout** — full app shell with left sidebar, topbar, and grid. Solves the 1.2 nav problem.
8. **`dropdown-user.html`** — user menu dropdown. Drop-in replacement for the current `[LOGOUT]` button.

Not useful (skip):
- NFT components (6 files)
- Marketing sections (faq, pricing)
- Account / billing pages (bot has no user accounts)
- `share/` and most of `img/`

---

## Section 3 — Reusability assessment

### 3.1 Worth pulling in

| Satoshi primitive | ZMN use case | Why |
|---|---|---|
| `pages/dashboard.html` layout (sidebar + topbar + grid) | App shell that links main/analytics/wallet dashboards | Fixes 1.2 nav gap. This alone justifies the template import. |
| `card-stat-*.html` | Topbar KPI cards (or sidebar summary cards) | Consistent framing for 8+ KPI metrics. |
| `card-chart-*.html` | Equity Curve, P/L Distribution, Win Rate bars | Polished chart containers with title/subtitle slots. |
| `card-latest-orders.html` | Recent Trades table | Data-table styling beats hand-rolled. |
| `card-activity-timeline.html` | Signal Stream | Time-ordered event list with icons. |
| `card-balance.html` | Wallet Balance hero widget | Big-number with sub-stats. |
| Webpixels utility classes | General layout | `d-flex gap-3`, `text-xs`, `rounded-3` — save hand-rolling. |
| Bootstrap Icons | Replace emoji + ASCII markers | Consistent iconography. |
| Satoshi font (Fontshare CDN) | Display type (optional) | Distinctive — already paid for via theme. |
| `img/crypto/color/*.svg` | Token icons next to trade rows | Per-token SOL/USDT/USDC icons. |

### 3.2 NOT worth pulling in

- **The "out-of-the-box Satoshi aesthetic."** It's a polished but generic DeFi-exchange-dashboard look. The `frontend-design` skill explicitly warns: *"NEVER use generic AI-generated aesthetics... predictable layouts and component patterns, and cookie-cutter design that lacks context-specific character."* Using the theme's default palette + layout would produce a dashboard indistinguishable from 100 other DeFi apps. **Pull the components, not the aesthetic.**
- **NFT / auction / bid components** — wrong domain.
- **Marketing pages, pricing, terms** — wrong purpose.
- **Build tooling inheritance** — there's none to inherit. Keep vanilla.
- **`main.js` (712KB Webpixels bundle)** — being deleted this session. Write minimal custom glue instead.

### 3.3 What stays custom no matter which direction

- **8-theme system.** It's a working, well-engineered user preference. Whatever redesign direction Jay picks, this should survive — reinterpreted as 8 accent variations on a unified base, not rebuilt.
- **Chart.js integration.** Already working, already wired to theme variables.
- **Self-contained single-HTML pattern.** No build step. No npm. Vanilla JS fetches + DOM updates. This is a ZMN superpower — keep it.
- **Authenticated fetch wrapper** (`authHeaders()`, JWT in localStorage). Existing pattern works; don't rebuild.
- **Paper/Live mode toggle** in the topbar. Functional and prominently placed; keep.

---

## Section 4 — Three redesign concepts

Principles from the `frontend-design` skill applied to every concept:

- **Distinctive typography** (not Arial, Inter, Roboto, or system stacks)
- **Atmosphere and depth** (backgrounds are not flat)
- **Bold colour commitment** (dominant + sharp accent)
- **Information density earned** (asymmetric grid, hierarchy)
- **Motion used at high-impact moments**, not scattered micro-interactions
- **Execute the vision with precision**

---

### Concept A — "Trading Desk"

*Bloomberg Terminal density × Linear dark polish. Refined, fast, professional.*

**Design language reference:** Bloomberg Terminal's information density + Linear's visual polish + Geist app / Vercel dashboard restraint.

**Vision in one paragraph:** A dense, dark, professional trading terminal that feels like equipment. Numbers-first. Fixed-width for data, proportional sans for chrome. One sharp accent (cyan) flips to amber in warning states, rose-gold in P/L-red. No ornament that doesn't earn its place. Scanline overlay is DROPPED — this concept trades retro charm for credibility. The payoff: the dashboard starts to feel like something Jay could put on a second monitor and leave on all day without it being exhausting.

**Typography:**

- Display: **JetBrains Mono** for all numeric data (tickers, P/L, mcap) at mono 500/700 weight.
- Body: **Söhne** (or **IBM Plex Sans** as free alternative) at 400/500 for labels and chrome.
- This pairing is deliberately two-monospace-feeling fonts — Plex Sans has mono-adjacent x-heights that sync with Plex Mono numbers at small sizes. Reads like a terminal without being one.

**Colour:**

- Base: `#0A0E13` (near-black cool slate), elevation layers at `#111821` / `#18222E`.
- Borders: `#1F2A38` → `#2D3D52` on hover.
- Body text: `#E6EEF7`. Muted: `#7A8694`.
- Accent (default / P/L-positive): `#5EEAD4` (teal-cyan).
- Warning: `#F59E0B` (amber).
- Danger (P/L-negative): `#F43F5E` (rose).
- **8-theme system reinterpreted:** each theme rotates only the accent hue while the base stays unified. Acid → `#A3FF12`, Amber → `#F59E0B`, Cyan → `#5EEAD4`, Magenta → `#E879F9`, Red → `#F43F5E`, Purple → `#A78BFA`, Orange → `#FB923C`, Blue → `#60A5FA`. One base, eight accents. Preserves Jay's preference system without fragmenting the visual identity.

**Layout:**

- **Sidebar left** (64px collapsed, 200px expanded): nav links for Main / Analytics / Wallet / Signals, plus pinned wallet balance at the bottom. SOLVES the three-dashboard navigation gap.
- **Topbar sticky** (48px): status pill, mode toggle, SOL/CFGI/WR/ML chips, clock, theme switcher, logout.
- **Main grid 12-col on desktop, 8-col on laptop, 4-col tablet, 1-col mobile**: hero equity curve spans 8 cols; side column (4 cols) stacks Session Stats + Signal Funnel. Row 2 is ML + Personality + Governance in a 4-col tri-split. Row 3 is Open Positions (data table, 8 cols) + Recent Trades (8 cols, below). Etc.
- **Widget chrome:** pull Satoshi's `card-chart-1` shape (title top-left, subtitle top-right, chart below). Customize palette to match.

**Atmosphere/depth:**

- Subtle noise-grain texture overlay (`background-image: url('data:image/svg+xml;utf8,<svg>...</svg>')` with 3% opacity) — gives surface-finish, kills flat-screen feel.
- Panel borders use a 1px inner highlight at the top (`box-shadow: inset 0 1px 0 rgba(255,255,255,0.03)`) — the "bevel from below a light source" trick that looks like equipment.
- Hover states: border brightens 1 step + subtle y-offset `translate(0,-1px)`. Zero glow — this concept is restrained.

**Motion:**

- **One orchestrated reveal on load:** stagger the panel entries with `animation-delay: calc(var(--i) * 40ms)`. Fade + translate-y 8px. Completes in 600ms. Feels like equipment booting.
- Number updates: brief flash of accent-colour background on the `.value` element when it changes (100ms), nothing more.
- No scroll-triggered anything. No hover wobble.

**Satoshi components pulled:**

- `card-chart-1` (template) repainted → equity curve panel, P/L distribution, win-rate-by-regime.
- `card-latest-orders` → Recent Trades table shell.
- `card-stat-4` (single-number card) → topbar KPI chips.
- `dropdown-filters` → Recent Trades filter UI.
- `pages/dashboard.html` layout → app shell sidebar + topbar.

**What stays custom:** theme-rotation logic, chart theme variable bindings, authenticated fetch, paper/live mode toggle, all the `/api/*` data wiring.

**Complexity:** **3-day rebuild.** Day 1: app shell + sidebar + topbar + theme system. Day 2: all 14 panels ported from current HTML into new chrome. Day 3: Chart.js theming, polish, testing.

**HTML skeleton (conceptual, not full implementation):**

```html
<!DOCTYPE html>
<html lang="en" data-theme="acid">
<head>
  <meta charset="UTF-8">
  <title>ZMN BOT — Trading Desk</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3/dist/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10/font/bootstrap-icons.css">
  <link rel="stylesheet" href="https://api.fontshare.com/v2/css?f=jetbrains-mono@400,500,700&f=satoshi@400,500,700&display=swap">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
  <style>
    :root {
      --bg-0: #0A0E13; --bg-1: #111821; --bg-2: #18222E;
      --bd: #1F2A38; --bd-hi: #2D3D52;
      --fg: #E6EEF7; --muted: #7A8694;
      --accent: #5EEAD4;       /* flips per theme */
      --warn: #F59E0B;
      --danger: #F43F5E;
      --font-mono: "JetBrains Mono", ui-monospace, monospace;
      --font-sans: "Satoshi", -apple-system, sans-serif;
    }
    [data-theme="amber"]   { --accent: #F59E0B; }
    [data-theme="cyan"]    { --accent: #5EEAD4; }
    [data-theme="magenta"] { --accent: #E879F9; }
    /* ...six more themes, identical structure... */
    html, body {
      background: var(--bg-0); color: var(--fg);
      font-family: var(--font-sans);
      min-height: 100vh; margin: 0;
      background-image:
        url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence baseFrequency='0.9'/></filter><rect width='200' height='200' filter='url(%23n)' opacity='0.03'/></svg>");
    }
    .num, .value, .price, .pnl { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .app { display: grid; grid-template-columns: 200px 1fr; min-height: 100vh; }
    .sidebar {
      background: var(--bg-1); border-right: 1px solid var(--bd);
      padding: 16px 12px;
    }
    .sidebar-brand { font-weight: 700; letter-spacing: 0.04em; margin-bottom: 24px; }
    .sidebar nav a {
      display: flex; align-items: center; gap: 10px;
      padding: 8px 12px; border-radius: 6px;
      color: var(--muted); text-decoration: none; font-size: 14px;
    }
    .sidebar nav a.active, .sidebar nav a:hover {
      background: var(--bg-2); color: var(--fg);
    }
    .topbar {
      display: flex; gap: 16px; align-items: center;
      padding: 10px 20px; border-bottom: 1px solid var(--bd);
      background: rgba(10,14,19,0.8); backdrop-filter: blur(8px);
      position: sticky; top: 0;
    }
    .kpi-chip {
      display: flex; gap: 6px; font-size: 13px;
      padding: 4px 10px; border: 1px solid var(--bd); border-radius: 6px;
    }
    .kpi-chip .label { color: var(--muted); text-transform: uppercase; font-size: 10px; letter-spacing: 0.06em; }
    .grid {
      display: grid; gap: 16px; padding: 20px;
      grid-template-columns: repeat(12, 1fr);
    }
    .panel {
      background: var(--bg-1);
      border: 1px solid var(--bd);
      border-radius: 8px;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
      padding: 16px 18px;
      transition: border-color 120ms ease, transform 120ms ease;
      animation: panel-in 360ms cubic-bezier(.2,.7,.2,1) both;
      animation-delay: calc(var(--i, 0) * 40ms);
    }
    .panel:hover { border-color: var(--bd-hi); transform: translateY(-1px); }
    .panel-title { font-size: 11px; letter-spacing: 0.08em; color: var(--muted); text-transform: uppercase; margin-bottom: 10px; }
    .panel-value { font-family: var(--font-mono); font-size: 32px; font-weight: 500; }
    .positive { color: var(--accent); } .negative { color: var(--danger); }
    .span-8 { grid-column: span 8; } .span-4 { grid-column: span 4; } .span-6 { grid-column: span 6; }
    @keyframes panel-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
    @media (max-width: 960px) { .app { grid-template-columns: 1fr; } .span-8,.span-6,.span-4 { grid-column: span 1; } }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="sidebar-brand">ZMN<span style="color:var(--accent)">·</span>BOT</div>
      <nav>
        <a class="active"><i class="bi bi-bar-chart-fill"></i> Overview</a>
        <a><i class="bi bi-activity"></i> Analytics</a>
        <a><i class="bi bi-wallet2"></i> Wallet</a>
        <a><i class="bi bi-lightning-charge"></i> Signals</a>
        <a><i class="bi bi-diagram-3"></i> Whales</a>
      </nav>
      <div style="margin-top:auto; padding-top:24px; border-top: 1px solid var(--bd);">
        <div class="panel-title">Wallet</div>
        <div class="panel-value" style="font-size:20px;" id="sbBalance">-- SOL</div>
      </div>
    </aside>
    <main>
      <header class="topbar">
        <span class="kpi-chip"><span class="label">Mode</span><span class="num" style="color:var(--accent)">PAPER</span></span>
        <span class="kpi-chip"><span class="label">PnL</span><span class="num positive">+12.34</span></span>
        <span class="kpi-chip"><span class="label">SOL</span><span class="num">$184.21</span></span>
        <span class="kpi-chip"><span class="label">CFGI</span><span class="num">41</span></span>
        <span class="kpi-chip"><span class="label">WR</span><span class="num">38.6%</span></span>
        <span class="kpi-chip"><span class="label">ML</span><span class="num">0.64</span></span>
        <span style="flex:1"></span>
        <span class="num" id="clock">22:14:09</span>
        <select id="theme"><!-- 8 options --></select>
        <button>LOGOUT</button>
      </header>
      <div class="grid">
        <section class="panel span-8" style="--i:1">
          <div class="panel-title">Equity curve · daily</div>
          <canvas id="equity" height="220"></canvas>
        </section>
        <section class="panel span-4" style="--i:2">
          <div class="panel-title">Session</div>
          <div class="panel-value positive">+0.82 SOL</div>
          <!-- stat rows -->
        </section>
        <section class="panel span-4" style="--i:3"><div class="panel-title">ML</div>…</section>
        <section class="panel span-4" style="--i:4"><div class="panel-title">Personalities</div>…</section>
        <section class="panel span-4" style="--i:5"><div class="panel-title">Governance</div>…</section>
        <section class="panel span-8" style="--i:6">
          <div class="panel-title">Open positions</div>
          <table class="table-tight" id="positions"><!-- ported from current dashboard --></table>
        </section>
        <section class="panel span-4" style="--i:7"><div class="panel-title">Signal funnel</div>…</section>
        <section class="panel span-8" style="--i:8"><div class="panel-title">Recent trades</div>…</section>
        <section class="panel span-4" style="--i:9"><div class="panel-title">API health</div>…</section>
      </div>
    </main>
  </div>
</body>
</html>
```

**Trade-off vs current retro CRT:**

- **Gains:** legibility at distance, professional polish, trivially-scannable hierarchy, proper navigation between three dashboards, better chart readability, less eye fatigue over long sessions.
- **Loses:** nostalgia / character / "this feels like 1982-era Bloomberg." The scanline overlay and VT323 font were memorable; this concept is intentionally not.

---

### Concept B — "Editorial Terminal"

*Magazine-editorial typography × trading-terminal data density. Maximal, cinematic, character-forward. The ambitious one.*

**Design language reference:** Stripe Press / Bloomberg Businessweek editorial pages / Rainmeter live-telemetry skins / the opening credits of a 1970s control-room sci-fi film. NYT Connections aesthetic. Think "what if the FT did a trading terminal."

**Vision in one paragraph:** Walk in, see one enormous serif number filling a third of the screen — current wallet equity — slowly ticking, like a flight-deck altimeter. Underneath it, a curated hierarchy: hero equity chart with a subtle noise texture, then a staggered grid of secondary metrics, then a Bloomberg-density data tail. Typography is extreme: a distinctive serif display face for the big numbers, a geometric mono for everything tabular, a single opinionated body sans. Backgrounds are never flat — grain, subtle gradients, panel-edge highlights. The 8-theme system is reinterpreted as 8 SEASONS: each theme is a full palette (not just an accent swap) — "Acid Rain," "Sodium Vapour," "Ice Station," "Blood Orange," "Plum Noir," "Phosphor," "Prussian," "Mercury." This is the concept for Jay's stated "shit hot fantastic."

**Typography:**

- Display (big numbers, section titles): **PP Editorial New** (Pangram Pangram, free for personal use). Fallback: **Canela Deck** or **Source Serif 4**. Distinctive serif with a high contrast stroke — the face you'd see on a magazine cover.
- Tabular (all data): **JetBrains Mono** at 400/500. Tabular-nums variant locked.
- Body (chrome, labels): **Satoshi** (free on Fontshare — you already own it as part of the theme purchase).
- Three fonts is a lot, but they're clearly assigned to roles. Display + mono + sans = magazine-editorial canon.

**Colour — the 8-season palette:**

Example for the "Acid Rain" season (default):

- Base: `#0C1012` (ink-black with a green undertone)
- Paper: `#131A1D`
- Ink: `#ECF2EE`
- Muted: `#6A7E73`
- Accent: `#A3FF12` (neon chartreuse)
- Accent dim: `#4D7906`
- Positive: `#A3FF12`
- Negative: `#FF5B4C`

Each other season is a ground-up palette (not a hue rotation):

| Season | Base | Ink | Accent | Vibe |
|---|---|---|---|---|
| Acid Rain | black-green | white-green | chartreuse | cold weather, neon |
| Sodium Vapour | deep charcoal | warm ivory | FFB000 amber | night street lamp |
| Ice Station | slate-blue-black | frost white | 7FE7FF | sub-zero console |
| Blood Orange | warm dark umber | bone | FF6B2C | late-sunset trading floor |
| Plum Noir | deep aubergine | rose fog | E17AFF | cinematic, luxurious |
| Phosphor | paper-black | phosphor-green | 00FF41 | THE retro CRT, preserved |
| Prussian | deep prussian blue | pale steel | 60A5FA | naval-bridge |
| Mercury | near-white | graphite | 222 ink | light mode — editorial print |

**Layout:**

- **Topbar** is quiet — just nav pills and clock. No KPIs here.
- **Hero row** fills the top quarter of the viewport: left-aligned editorial serif reading "EQUITY" label above a gigantic number (`50.95 SOL`), sub-label showing 24h delta with Mono type. Right side: equity sparkline, 120px tall, with a translucent gradient fill.
- **Second row** (asymmetric 2/3 + 1/3): full-width Daily Equity Curve (tall, 320px) on left; vertical stack on right showing Today's Session stats as a big-type list (serif labels, mono values, generous line-height).
- **Third row** (3-column): Signal Funnel as a numbered hierarchy (editorial-style list with drop caps — "01 raw", "02 scored", "03 gated"), ML Status as a circle gauge with serif number inside, Personality Stats as a 3-row comparison chart with each personality's name set in italic serif.
- **Fourth row** (12-col data strip): Open Positions as a dense table with Mono, icons, sparkline per row.
- **Fifth row** (2-col): Recent Trades (full width dense table) + Signal Stream (scrolling activity log with serif timestamps).

Asymmetry, deliberate white space, and type-hierarchy DO the heavy lifting here. Panel boundaries are hairline (`1px solid rgba(255,255,255,0.06)`) — barely visible. What separates sections is whitespace and typography, not boxes.

**Atmosphere/depth:**

- Per-season grain overlay (SVG noise, 4% opacity, seasonal tint) — "Ice Station" has a cold blue tint, "Blood Orange" has amber warmth.
- Top of viewport: soft vertical gradient from `var(--base)` to a slightly darker top edge — "horizon" effect, 200px tall, subtle.
- On load: hero number animates from `0` to current value over 900ms with an `ease-out-expo` curve. This is the ONE big motion moment.
- Panel entries cascade on first render with 60ms stagger — similar to Concept A but slower and more deliberate.
- Accent color has a soft glow on specific elements only (the live "WALLET" number pulses very subtly, 4-second cycle, 2% opacity delta). Restrained.

**Motion:**

- Hero number animated count-up on load.
- Sparkline draws line animation (1.2s) on load.
- Section headers fade + translate-y on first render.
- Chart updates: new data points animated in over 400ms.
- NO hover glows, NO scroll-triggered animations, NO cursor followers, NO generic micro-interactions.

**Satoshi components pulled:**

- `card-chart-2` → hero Equity Curve (bigger version with gradient fill)
- `card-balance` → hero WALLET module (adapted as big editorial type)
- `card-activity-timeline` → Signal Stream
- `card-latest-orders` → Recent Trades base structure
- `card-stat-chart-1` → secondary KPI cards (tiny sparkline + big number)

**What stays custom:** everything aesthetic. The editorial type system, the 8-season palettes, the grain overlays, the hero count-up. The Satoshi components are just grids we pour into.

**Complexity:** **1-week overhaul.** Day 1-2: typography system + 8-season palette engine (major work — each season needs hand-tuned color pairs, not generated). Day 3: hero row + Equity Curve — nail these, they're 80% of the visual impact. Day 4-5: secondary panels + data tables. Day 6: Chart.js deep theming (per-season chart palettes). Day 7: polish, accessibility audit, perf check on the grain overlay.

**HTML skeleton:**

```html
<!DOCTYPE html>
<html lang="en" data-season="acid-rain">
<head>
  <meta charset="UTF-8"><title>ZMN — Trading Log</title>
  <link rel="stylesheet" href="https://api.fontshare.com/v2/css?f=satoshi@400,500,700,900&f=editorial-new@400,700&f=jetbrains-mono@400,500&display=swap">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
  <style>
    :root {
      --base: #0C1012; --paper: #131A1D;
      --ink: #ECF2EE; --muted: #6A7E73;
      --accent: #A3FF12; --accent-dim: #4D7906;
      --negative: #FF5B4C;
      --serif: "Editorial New","Canela Deck",Georgia,serif;
      --mono: "JetBrains Mono",ui-monospace,monospace;
      --sans: "Satoshi",-apple-system,sans-serif;
      --grain: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='300' height='300'><filter id='n'><feTurbulence baseFrequency='0.85' numOctaves='2'/></filter><rect width='300' height='300' filter='url(%23n)' opacity='0.04'/></svg>");
    }
    [data-season="sodium-vapour"] {
      --base:#141210; --paper:#1C1915; --ink:#F4E9D4; --muted:#8C7955;
      --accent:#FFB000; --accent-dim:#7A5400; --negative:#FF4B2E;
    }
    [data-season="ice-station"] {
      --base:#0A0F1A; --paper:#101828; --ink:#DFEAF5; --muted:#5F7594;
      --accent:#7FE7FF; --accent-dim:#2E6B85; --negative:#FF5B7B;
    }
    /* ...five more seasons... */

    * { box-sizing: border-box; margin: 0; }
    html, body {
      background: var(--base); color: var(--ink);
      font-family: var(--sans); font-size: 15px; line-height: 1.5;
      min-height: 100vh;
    }
    body::before { /* grain overlay */
      content: ""; position: fixed; inset: 0; pointer-events: none;
      background-image: var(--grain); z-index: 1000;
    }
    body::after { /* top horizon gradient */
      content: ""; position: fixed; top: 0; left: 0; right: 0; height: 220px;
      background: linear-gradient(to bottom, color-mix(in srgb, var(--base) 88%, black) 0%, transparent 100%);
      pointer-events: none; z-index: 0;
    }
    .serif { font-family: var(--serif); font-weight: 400; letter-spacing: -0.01em; }
    .mono  { font-family: var(--mono); font-variant-numeric: tabular-nums; }
    .nav {
      display:flex; gap: 28px; align-items:center;
      padding: 20px 48px;
      font-size: 13px; letter-spacing: 0.08em; text-transform: uppercase;
    }
    .nav a { color: var(--muted); text-decoration: none; }
    .nav a.active { color: var(--ink); border-bottom: 1px solid var(--accent); padding-bottom: 4px; }

    .shell { padding: 0 48px 48px; max-width: 1600px; margin: 0 auto; }
    .hero {
      display: grid; grid-template-columns: 1.2fr 1fr; gap: 48px;
      padding: 32px 0 48px; border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    .hero-label { font-size: 12px; letter-spacing: 0.16em; color: var(--muted); text-transform: uppercase; margin-bottom: 16px; }
    .hero-value {
      font-family: var(--serif); font-size: clamp(80px, 12vw, 180px);
      font-weight: 400; letter-spacing: -0.02em; line-height: 0.95;
      color: var(--ink);
    }
    .hero-unit { font-family: var(--serif); font-size: 0.3em; color: var(--muted); letter-spacing: 0; margin-left: 0.2em; vertical-align: 0.9em; }
    .hero-delta { font-family: var(--mono); font-size: 15px; margin-top: 14px; color: var(--accent); }
    .hero-spark { height: 160px; position: relative; opacity: 0; animation: spark-in 1.2s .3s ease-out both; }

    .section-head {
      display: flex; align-items: baseline; justify-content: space-between;
      margin: 48px 0 20px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px;
    }
    .section-head h2 { font-family: var(--serif); font-size: 28px; font-weight: 400; letter-spacing: -0.01em; }
    .section-head .timestamp { font-family: var(--mono); font-size: 12px; color: var(--muted); }

    .row { display: grid; gap: 24px; }
    .row.two-thirds { grid-template-columns: 2fr 1fr; }
    .row.thirds     { grid-template-columns: repeat(3, 1fr); }
    .row.full       { grid-template-columns: 1fr; }

    .panel {
      padding: 20px 0;
      animation: rise 600ms cubic-bezier(.2,.7,.2,1) both;
      animation-delay: calc(var(--i,0) * 60ms);
    }
    .panel-big-number { font-family: var(--serif); font-size: 56px; line-height: 1; margin: 8px 0 12px; }
    .panel-sub { font-family: var(--mono); font-size: 13px; color: var(--muted); }

    .funnel {
      counter-reset: step; list-style: none; padding: 0;
    }
    .funnel li {
      counter-increment: step;
      display: grid; grid-template-columns: auto 1fr auto; gap: 24px; align-items: baseline;
      padding: 14px 0; border-top: 1px solid rgba(255,255,255,0.06);
    }
    .funnel li::before {
      content: counter(step, decimal-leading-zero);
      font-family: var(--serif); font-size: 28px; color: var(--accent-dim);
    }
    .funnel li span.label { font-family: var(--serif); font-size: 20px; }
    .funnel li span.val { font-family: var(--mono); font-size: 18px; color: var(--ink); }

    .tight-table { width: 100%; font-family: var(--mono); font-size: 13px; }
    .tight-table th, .tight-table td { text-align: left; padding: 8px 12px; border-top: 1px solid rgba(255,255,255,0.05); }
    .tight-table th { color: var(--muted); font-weight: 400; text-transform: uppercase; letter-spacing: 0.06em; font-size: 11px; }
    .positive { color: var(--accent); } .negative { color: var(--negative); }

    @keyframes rise  { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
    @keyframes spark-in { to { opacity: 1; } }
  </style>
</head>
<body>
  <nav class="nav">
    <span class="serif" style="font-size:22px;">ZMN.</span>
    <a class="active">Overview</a><a>Analytics</a><a>Wallet</a><a>Signals</a>
    <span style="flex:1"></span>
    <span class="mono" id="clock">22:14:09</span>
    <select id="season" aria-label="Season">
      <option value="acid-rain">Acid Rain</option>
      <option value="sodium-vapour">Sodium Vapour</option>
      <option value="ice-station">Ice Station</option>
      <option value="blood-orange">Blood Orange</option>
      <option value="plum-noir">Plum Noir</option>
      <option value="phosphor">Phosphor</option>
      <option value="prussian">Prussian</option>
      <option value="mercury">Mercury</option>
    </select>
  </nav>

  <div class="shell">

    <header class="hero">
      <div>
        <div class="hero-label">Equity · Paper Mode</div>
        <div class="hero-value" id="heroEquity">50.95<span class="hero-unit">SOL</span></div>
        <div class="hero-delta mono">+0.82 SOL <span style="color:var(--muted)">(24h · +1.6%)</span></div>
      </div>
      <div class="hero-spark"><canvas id="equitySpark"></canvas></div>
    </header>

    <div class="section-head">
      <h2>Today's session</h2>
      <span class="timestamp">Updated 22:14 AEDT</span>
    </div>
    <div class="row thirds">
      <section class="panel" style="--i:1">
        <div class="panel-sub">Trades</div>
        <div class="panel-big-number mono">47</div>
      </section>
      <section class="panel" style="--i:2">
        <div class="panel-sub">Win rate</div>
        <div class="panel-big-number mono">38.6<span style="font-size:0.4em;color:var(--muted)">%</span></div>
      </section>
      <section class="panel" style="--i:3">
        <div class="panel-sub">Best trade</div>
        <div class="panel-big-number mono positive">+0.74</div>
      </section>
    </div>

    <div class="section-head">
      <h2>Signal funnel</h2>
      <span class="timestamp">Last 24h</span>
    </div>
    <ol class="funnel">
      <li><span class="label serif">Raw tokens observed</span><span class="val mono">3,812</span></li>
      <li><span class="label serif">Scored by ML</span><span class="val mono">1,294</span></li>
      <li><span class="label serif">Passed gates</span><span class="val mono">287</span></li>
      <li><span class="label serif">Executed</span><span class="val mono">47</span></li>
    </ol>

    <div class="section-head">
      <h2>Open positions</h2>
      <span class="timestamp">3 active</span>
    </div>
    <table class="tight-table">
      <thead><tr><th>Symbol</th><th>Entered</th><th>Hold</th><th>Entry</th><th>Mark</th><th>P/L</th></tr></thead>
      <tbody><!-- rows --></tbody>
    </table>

    <!-- …remaining panels follow the same editorial section-head + grid pattern… -->

  </div>

  <script>
    // Hero count-up
    (function(){
      const el = document.getElementById('heroEquity');
      const target = 50.95; let cur = 0;
      const start = performance.now(); const dur = 900;
      function tick(t){
        const p = Math.min(1, (t - start)/dur);
        const eased = 1 - Math.pow(1-p, 4);
        cur = target * eased;
        el.innerHTML = cur.toFixed(2) + '<span class="hero-unit">SOL</span>';
        if (p < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    })();
  </script>
</body>
</html>
```

**Trade-off vs current retro CRT:**

- **Gains:** distinctive. Unforgettable. Feels like it was designed by a person with a point of view. Solves the navigation gap. Keeps "Phosphor" as one of 8 seasons so the retro CRT is never lost — it's just one of eight modes now.
- **Loses:** maintenance cost is higher (3 fonts, 8 hand-tuned palettes, grain overlay). Serif display at 120px+ means long token names will wrap awkwardly unless constrained. The big-type hero takes screen space that dense-view users might prefer to spend on data.

---

### Concept C — "Unified Cockpit"

*Linear-style refined minimalism with a proper information architecture.*

**Design language reference:** Linear's dashboard / Notion's data density / Cron.com app chrome / Geist app. Intentionally restrained — beautiful by subtraction.

**Vision in one paragraph:** Solve the three-dashboards-no-navigation problem first and let everything else flow from there. One app shell, sidebar left, three routes (Overview / Analytics / Wallet) that swap the main content area. Near-monochrome greyscale base with a single sharp accent (violet is the safe Linear choice; consider chartreuse for more character). Small fonts, tight leading, generous whitespace. The scanline is DROPPED, the 8-theme system is DROPPED, replaced with a "light / dark + accent" system — user picks base mode (light or dark) and one accent hue. Simpler to maintain, faster to iterate on. This is the "highest value-per-effort" direction.

**Typography:**

- Display: **Söhne** or **Geist** (Vercel's free typeface — very good). Fallback: **IBM Plex Sans**.
- Body: same as display (Söhne/Geist scales beautifully; you don't need a second face).
- Mono (numeric data): **Geist Mono** (ships with Geist).
- Two fonts total. Trade off: less editorial, more "product."

**Colour:**

- Light mode base: `#FAFAFA` → `#FFFFFF` → `#F4F4F5`
- Dark mode base: `#09090B` → `#18181B` → `#27272A`
- Muted: `#71717A`
- Accent (default): `#84CC16` (chartreuse — gives it character vs the Linear-violet default)
- P/L positive: accent hue
- P/L negative: `#EF4444` (red-500)
- User picks from 6 accent presets (violet, chartreuse, amber, cyan, rose, blue) — collapses the 8-theme system.

**Layout:**

- **Persistent left sidebar** (224px, collapsible to 64px icon rail):
  - Top: brand + mode toggle (paper/live) as a prominent segmented control.
  - Middle: nav — Overview, Analytics, Wallet, Signals, Whales, Settings.
  - Bottom: wallet balance summary + logout.
- **Thin topbar** (40px): breadcrumb + status pill + live-update timestamp + theme picker.
- **Main content** routes to three views:
  - **Overview** → current 14 panels, but grouped into 3 tabs: "Now" (session + open positions + signals), "Performance" (equity curve + WR + P/L distribution + exit analysis), "Systems" (ML + governance + API health + personality stats).
  - **Analytics** → re-home the current dashboard-analytics.html content.
  - **Wallet** → re-home the current dashboard-wallet.html content.

Tabs let Jay collapse the cognitive load of 14 panels into 4-5 at a time.

**Atmosphere/depth:**

- No grain. No CRT. No gradient. Pure flat surfaces, hairline borders (`1px solid` at 5% opacity), careful spacing.
- Elevation communicated by a single shadow on hovered rows/cards (`box-shadow: 0 2px 8px rgba(0,0,0,0.06)`), not by multiple layers.
- Dark mode: same structure, near-black surfaces.

**Motion:**

- Route transitions: 180ms fade + slight y-offset. Nothing else.
- Hover: border 1 step brighter, 80ms.
- No load reveal. No count-up. No scroll triggers. Stillness is the feature.

**Satoshi components pulled:**

- `pages/dashboard.html` base layout (sidebar + topbar + tabs) → foundation.
- `card-stat-3.html` → KPI tiles.
- `card-chart-1.html` → chart cards.
- `card-activity-timeline.html` → Signal Stream.
- `card-latest-orders.html` → Recent Trades.

**What stays custom:** routing logic (vanilla JS hash router), dark/light toggle, accent picker, Chart.js theming, paper/live toggle.

**Complexity:** **3-day rebuild.** Day 1: app shell + sidebar + routing + light/dark toggle. Day 2: Overview tabs + port 14 panels. Day 3: Analytics + Wallet routes, Chart.js theming, polish.

**HTML skeleton:**

```html
<!DOCTYPE html>
<html lang="en" data-theme="dark" data-accent="chartreuse">
<head>
  <meta charset="UTF-8"><title>ZMN — Overview</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10/font/bootstrap-icons.css">
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500&display=swap">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
  <style>
    :root {
      --bg-0: #09090B; --bg-1: #18181B; --bg-2: #27272A;
      --bd: rgba(255,255,255,0.06); --bd-hi: rgba(255,255,255,0.10);
      --fg: #FAFAFA; --muted: #A1A1AA;
      --accent: #84CC16;        /* chartreuse default */
      --negative: #EF4444;
      --font: "Geist", -apple-system, sans-serif;
      --mono: "Geist Mono", ui-monospace, monospace;
    }
    [data-theme="light"] {
      --bg-0: #FAFAFA; --bg-1: #FFFFFF; --bg-2: #F4F4F5;
      --bd: rgba(0,0,0,0.06); --bd-hi: rgba(0,0,0,0.12);
      --fg: #09090B; --muted: #71717A;
    }
    [data-accent="violet"]    { --accent: #8B5CF6; }
    [data-accent="chartreuse"]{ --accent: #84CC16; }
    [data-accent="amber"]     { --accent: #F59E0B; }
    [data-accent="cyan"]      { --accent: #06B6D4; }
    [data-accent="rose"]      { --accent: #F43F5E; }
    [data-accent="blue"]      { --accent: #3B82F6; }

    * { box-sizing: border-box; margin: 0; }
    html, body { background: var(--bg-0); color: var(--fg); font-family: var(--font); font-size: 14px; min-height: 100vh; }
    .mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }

    .app { display: grid; grid-template-columns: 224px 1fr; min-height: 100vh; }
    .sidebar { background: var(--bg-1); border-right: 1px solid var(--bd); display:flex; flex-direction:column; padding: 14px; }
    .brand { font-weight: 600; font-size: 15px; letter-spacing: -0.01em; padding: 4px 8px 18px; }
    .brand .dot { display:inline-block; width:6px; height:6px; border-radius:3px; background:var(--accent); margin-right:8px; vertical-align:1px; }
    .mode-toggle { display: grid; grid-template-columns: 1fr 1fr; padding: 4px; background: var(--bg-2); border-radius: 8px; margin-bottom: 18px; }
    .mode-toggle button { background: transparent; border: 0; color: var(--muted); padding: 6px; border-radius: 6px; font-family: var(--font); font-size: 12px; cursor: pointer; }
    .mode-toggle button.active { background: var(--bg-0); color: var(--fg); box-shadow: 0 1px 2px rgba(0,0,0,0.1); }
    nav.main a {
      display: flex; align-items: center; gap: 10px; padding: 7px 10px;
      border-radius: 6px; color: var(--muted); text-decoration: none;
      font-size: 13.5px; margin-bottom: 2px;
    }
    nav.main a.active { background: var(--bg-2); color: var(--fg); }
    nav.main a:hover:not(.active) { color: var(--fg); }
    nav.main .shortcut { margin-left:auto; font-size: 11px; color: var(--muted); font-family: var(--mono); }
    .sidebar .wallet { margin-top: auto; padding: 12px; border-top: 1px solid var(--bd); }

    .topbar { display:flex; align-items:center; gap: 14px; padding: 0 20px; height: 44px; border-bottom: 1px solid var(--bd); background: var(--bg-1); }
    .crumbs { font-size: 13px; color: var(--muted); }
    .crumbs .current { color: var(--fg); }
    .status-pill { display:flex; gap:6px; align-items:center; padding: 2px 10px; border: 1px solid var(--bd); border-radius: 999px; font-size: 12px; }
    .status-pill .dot { width:6px; height:6px; border-radius: 3px; background: var(--accent); }

    .content { padding: 20px; }
    .tabs { display:flex; gap: 2px; border-bottom: 1px solid var(--bd); margin-bottom: 20px; }
    .tabs button {
      background: transparent; border: 0; color: var(--muted);
      padding: 10px 14px; font-family: var(--font); font-size: 13px; cursor: pointer;
      border-bottom: 2px solid transparent; margin-bottom: -1px;
    }
    .tabs button.active { color: var(--fg); border-bottom-color: var(--accent); }

    .grid { display: grid; gap: 14px; grid-template-columns: repeat(12, 1fr); }
    .card {
      background: var(--bg-1); border: 1px solid var(--bd); border-radius: 10px;
      padding: 14px 16px;
      transition: border-color 80ms ease, box-shadow 120ms ease;
    }
    .card:hover { border-color: var(--bd-hi); box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
    .card h3 { font-size: 12px; color: var(--muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 8px; }
    .card .value { font-size: 22px; font-weight: 500; }
    .span-12 { grid-column: span 12; } .span-6 { grid-column: span 6; }
    .span-4 { grid-column: span 4; } .span-3 { grid-column: span 3; }
    .positive { color: var(--accent); } .negative { color: var(--negative); }
    @media (max-width: 900px) {
      .app { grid-template-columns: 1fr; }
      .sidebar { display:none; }
      [class^="span-"] { grid-column: span 1; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand"><span class="dot"></span>ZMN Bot</div>
      <div class="mode-toggle">
        <button class="active">Paper</button><button>Live</button>
      </div>
      <nav class="main">
        <a class="active"><i class="bi bi-grid"></i> Overview <span class="shortcut">1</span></a>
        <a><i class="bi bi-graph-up"></i> Analytics <span class="shortcut">2</span></a>
        <a><i class="bi bi-wallet2"></i> Wallet <span class="shortcut">3</span></a>
        <a><i class="bi bi-lightning"></i> Signals</a>
        <a><i class="bi bi-diagram-3"></i> Whales</a>
        <a><i class="bi bi-gear"></i> Settings</a>
      </nav>
      <div class="wallet">
        <div style="font-size:11px; color:var(--muted); margin-bottom:4px;">WALLET</div>
        <div class="mono" style="font-size:18px;">50.95 <span style="color:var(--muted);font-size:12px;">SOL</span></div>
        <div class="mono positive" style="font-size:12px;">+0.82 (24h)</div>
      </div>
    </aside>
    <main>
      <header class="topbar">
        <div class="crumbs">ZMN · <span class="current">Overview</span></div>
        <span class="status-pill"><span class="dot"></span>Live</span>
        <span style="flex:1"></span>
        <span class="mono" style="font-size:12px; color:var(--muted);">Updated 22:14:09 AEDT</span>
        <select id="accent" style="background:var(--bg-2); color:var(--fg); border:1px solid var(--bd); border-radius:6px; padding:2px 6px; font-size:12px;">
          <option value="chartreuse">◯ Chartreuse</option>
          <option value="violet">◯ Violet</option>
          <option value="amber">◯ Amber</option>
          <option value="cyan">◯ Cyan</option>
          <option value="rose">◯ Rose</option>
          <option value="blue">◯ Blue</option>
        </select>
      </header>
      <section class="content">
        <div class="tabs">
          <button class="active">Now</button>
          <button>Performance</button>
          <button>Systems</button>
        </div>
        <div class="grid">
          <article class="card span-3"><h3>Session P/L</h3><div class="value mono positive">+0.82</div></article>
          <article class="card span-3"><h3>Trades today</h3><div class="value mono">47</div></article>
          <article class="card span-3"><h3>Win rate</h3><div class="value mono">38.6%</div></article>
          <article class="card span-3"><h3>Open positions</h3><div class="value mono">3</div></article>
          <article class="card span-12"><h3>Equity curve</h3><canvas id="equity" height="220"></canvas></article>
          <article class="card span-6"><h3>Open positions</h3><!-- table --></article>
          <article class="card span-6"><h3>Signal stream</h3><!-- list --></article>
        </div>
      </section>
    </main>
  </div>
</body>
</html>
```

**Trade-off vs current retro CRT:**

- **Gains:** solves the navigation gap permanently. Dramatically lower maintenance. Light mode for daytime trading. Easier to add new panels without redesigning. Hits the "Linear-style clean professional look" directly.
- **Loses:** character. The current dashboard feels like Jay's bot — this one feels like a stock SaaS product. Retro CRT fans will hate it. The `frontend-design` skill principles would flag this concept's biggest risk: converging on Linear-default is exactly the "AI slop aesthetics" the skill warns about — the chartreuse accent default is a deliberate hedge against that.

---

## Section 5 — Jay's decision framework

### Which concept fits "shit hot fantastic" if complexity is no object

**Concept B — "Editorial Terminal."**

It's the one that makes someone pause when they see it. The editorial serif hero, the 8-season palette, the grain overlay — that's the direction with the highest ceiling on distinctive character. The `frontend-design` skill language: "bold maximalism and refined minimalism both work — the key is intentionality, not intensity." Concept B commits fully, Concept C commits fully, Concept A is the middle ground.

### Which concept is the highest value-per-effort

**Concept C — "Unified Cockpit."**

3 days to build. Solves the single biggest real problem (three disconnected dashboards). Lowest maintenance going forward. Light mode unlocks daytime comfort. If Jay wants to be trading next month, not designing next month, this is the choice.

### What the current retro CRT preserves that any redesign might lose

- **A coherent point-of-view.** The current dashboard is NOT generic; it's clearly Jay's bot, clearly opinionated. Replacing it with a Linear-clone (Concept C default) risks trading that for polish.
- **Zero build step.** Any redesign that accidentally pulls in Bootstrap JS + Choices.js + modal plugins makes the page heavier. All three concepts keep vanilla — enforce this in review.
- **The 8-theme system is user preference, not decoration.** Concept A preserves it (as 8 accent rotations). Concept B reinterprets it (as 8 full seasons, stronger). Concept C collapses it (6 accent presets, weaker). If Jay uses theme switching regularly, Concept C is a loss.
- **Phosphor / retro-CRT has earned its place.** Concept B's "Phosphor" season keeps it explicitly. Concept A's theme system can preserve it as one of the 8 accents applied to a greener base. Concept C drops it.

### Recommended next step

Paste the following into a follow-up session when you want to commit to one direction. Replace `<CHOICE>` with `A`, `B`, or `C`.

```
# ZMN dashboard — implementation of Concept <CHOICE>

Read docs/audits/DASHBOARD_REDESIGN_2026_04_19.md — this is a follow-up
to that report, building out Concept <CHOICE>.

Scope:
- Build the new dashboard.html as a drop-in replacement (keep dashboard-analytics.html
  and dashboard-wallet.html as is for now; we'll fold them into the app shell in
  a second session if Concept A or C is chosen).
- Pull Satoshi components listed in the report's Concept <CHOICE> section.
- Preserve existing /api/* wiring exactly — no backend changes.
- Preserve 8-theme system according to Concept <CHOICE>'s reinterpretation.
- Vanilla JS, Chart.js CDN, no build step.

Out of scope: services/, railway.toml, env vars, live mode.

Verification: load in browser, confirm all 18 /api/* endpoints render,
confirm theme switcher works, confirm login flow still redirects correctly.

Deliverable: one commit with dashboard.html replaced, one deploy, screenshot
back to Jay.
```

### My recommendation (not a decision — Jay's call)

**If this is going on public/shared surfaces (zmnbot.com for investors, demos, screenshots on social):** Concept B. It's the only one that photographs well.

**If this is Jay's working tool, watched 10+ hours a day, iterating on fast:** Concept C. Stillness and simplicity win when you live in the interface.

**If Jay wants to keep the retro-CRT spirit but level up the polish and solve the nav gap in one step:** Concept A. It's the least risky direction — the one that can't go wrong but also can't astonish.

Concept B is the one Jay explicitly asked for ("shit hot fantastic"). Aim there unless the week-long rebuild cost genuinely blocks other work.

---

## Appendix — skill usage notes

This report used principles from the `frontend-design` skill throughout Section 4:

- **"Don't converge on common choices (Space Grotesk, for example)."** None of the three concepts propose Space Grotesk. Concept A uses Söhne + JetBrains Mono. Concept B uses Editorial New + JetBrains Mono + Satoshi (three faces, magazine canon). Concept C uses Geist (Vercel's typeface, distinctive and free).
- **"Typography: Choose fonts that are beautiful, unique, and interesting. Avoid generic fonts like Arial and Inter."** All concepts avoid Inter and system stacks.
- **"Commit to a cohesive aesthetic. Dominant colors with sharp accents outperform timid, evenly-distributed palettes."** Every concept has a single dominant palette and one sharp accent. Concept B takes this furthest with 8 hand-tuned seasonal palettes.
- **"Motion: use animations at high-impact moments."** Concept A: one staggered load reveal. Concept B: hero count-up on load. Concept C: route transitions only. None scatter micro-interactions.
- **"Backgrounds & Visual Details: create atmosphere and depth rather than defaulting to solid colors."** Concept A: inner highlight + noise grain. Concept B: grain + horizon gradient. Concept C: deliberate minimalism (stillness as atmosphere).
- **"NEVER use generic AI-generated aesthetics... cliched color schemes (particularly purple gradients on white backgrounds)."** No purple gradients anywhere. No white-on-white with a pastel accent. Each concept's palette is an intentional choice.

This report did not use `webapp-testing` — structural analysis only this session.
Live in-browser verification belongs in the implementation session.
