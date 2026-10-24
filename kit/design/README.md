# iVendNext partner design kit — `ivn-kit` 0.1.0

Your page opens inside iVendNext: as a sheet on the till, as a page under the Desk header, or as a customer portal. This kit makes it look like our own screens. It is one CSS file and one optional JavaScript file. Plain CSS, small plain JavaScript, no framework, no build step, no npm package, no licensed UI library.

**When to use it:** any page of yours that a cashier, a back-office user or a retailer's customer sees inside iVendNext.

## 1. Include it

Copy `ivn-kit.css` (and `ivn-kit.js` if you want its behaviour) next to your page and serve them from your own host. Pin the version: the first line of each file says it.

```html
<link rel="stylesheet" href="ivn-kit.css">
<script src="ivn-kit.js"></script>        <!-- optional -->
<body class="ivn"> … </body>
```

## 2. Take the tenant's theme and language from your context

The page's signed context (`#ctx=…` in the URL fragment) carries `theme` and `lang`. Apply them before the page paints:

```js
var ctx = new URLSearchParams(location.hash.slice(1)).get("ctx");
var b64 = ctx.split(".")[0].replace(/-/g, "+").replace(/_/g, "/");
var payload = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(b64), function (c) { return c.charCodeAt(0); })));
ivnKit.applyTheme(payload.theme);   // { mode: "light" | "dark", vars: { "--ivn-primary": "#0b4d69", … } }
ivnKit.applyDir(payload.lang);      // "ar", "he", "fa", "ur" (any region) → right-to-left
```

The theme is only looks. `applyTheme` accepts only the variables marked ★ below, each only with a value of its kind: a colour as `#hex`, `rgb()` or `hsl()`; a length in `px`/`rem`/`em`; a font scale from 0.75 to 1.5. Anything containing `url(`, `;`, `{`, `}`, `<`, `>`, `\` or `expression` is refused. It returns `{applied, rejected}`. The names a partner page's context sends are accepted too and mapped onto the kit's: `--ivn-card` → `--ivn-surface`, `--ivn-ink` → `--ivn-text`, `--ivn-muted` → `--ivn-text-muted`, `--ivn-line` → `--ivn-border`, `--ivn-accent` → `--ivn-primary` and `--ivn-primary-strong` (a kit name given beside its context name wins). So `ivnKit.applyTheme(payload.theme)` draws the till's own colours as sent. **Every other context field must be verified by your backend before you trust it.**

## 3. The token contract

A page reads only these variables. ★ = the tenant's theme may set it.

| Variable | Used for |
|---|---|
| `--ivn-bg` ★ | page background |
| `--ivn-surface` ★ | cards, sheets, dialogs |
| `--ivn-surface-2` | table head, default button |
| `--ivn-border` ★ · `--ivn-border-strong` | hairlines · chip outlines |
| `--ivn-text` ★ · `--ivn-text-muted` ★ | body text · help, meta, placeholders |
| `--ivn-control-bg` · `--ivn-control-border` | field fill and outline |
| `--ivn-primary` ★ | accents, selected, toggle on |
| `--ivn-primary-strong` ★ · `--ivn-on-primary` ★ | primary button ground · its label |
| `--ivn-primary-tint` · `--ivn-link` · `--ivn-focus` ★ | selected rows · links · focus ring |
| `--ivn-danger` · `--ivn-danger-text` · `--ivn-danger-tint` | danger button · error text · error ground |
| `--ivn-pill-{grey,blue,green,orange,red}-{bg,ink}` | status pills |
| `--ivn-radius` ★ · `--ivn-radius-lg` ★ · `--ivn-radius-pill` | corners |
| `--ivn-font` · `--ivn-font-mono` · `--ivn-font-scale` ★ | type (1 = 14px body) |
| `--ivn-s1` … `--ivn-s6` | spacing 4 · 8 · 12 · 16 · 24 · 32 px |
| `--ivn-shadow-sm` · `--ivn-shadow-lg` · `--ivn-overlay` | elevation, dialog backdrop |

The values are in `ivn-kit.css` §1–2. Fonts are not themeable and the kit ships none: it uses Inter when the device has it, otherwise the system font.

## 4. Dark mode and right-to-left

- **Dark:** `data-theme="dark"` on `<html>` (`applyTheme` sets it from `theme.mode`). With no `data-theme`, the device's setting decides (`prefers-color-scheme`); `data-theme="light"` forces light.
- **Right-to-left:** `dir="rtl"` on `<html>` (`applyDir` sets it). The kit uses logical CSS only (`margin-inline`, `padding-inline`, `inset-inline`, `text-align: start`), so layouts flip by themselves. Give arrows and chevrons the class `ivn-flip-rtl`; never a magnifier, a tick or a logo.

## 5. Tokens only

A partner page uses no colour or font of its own: no `#hex`, `rgb()`, `hsl()` or named colour, no `font-family`. Use the classes, or `var(--ivn-…)` in your own layout CSS. Icons are inline SVG with `stroke="currentColor"` or `fill="currentColor"`. Run the check on your page before you send it: `tools/check_kit.sh your-page.html`. Besides tokens only, it checks the kit version your page loads (your own copy, at this kit's version), contrast on the colours your page sets itself, and the page drawn right-to-left.

## 6. Components (class names)

| Component | Classes |
|---|---|
| Page head (Desk) | `ivn-page-head` · `ivn-crumb` · `ivn-title` · `ivn-actions` |
| Card, form section | `ivn-card` · `ivn-section` · `ivn-section-title` · `ivn-grid` · `ivn-span-all` |
| Fields | `ivn-field` (+ `is-invalid`) · `ivn-label` · `ivn-req` · `ivn-input` · `ivn-select` · `ivn-textarea` · `ivn-help` · `ivn-error-text` · `ivn-check` · `ivn-toggle` + `ivn-toggle-track` |
| Link search | `ivn-link-search` around an `ivn-input`; `ivnKit.linkSearch(input, {search, onPick})` — `search(text)` is **your** function returning a Promise of `[{value, label, description}]`; the kit never calls the network |
| Buttons | `ivn-btn` · `ivn-btn-primary` · `ivn-btn-danger` · `ivn-btn-sm` · `ivn-btn-icon` (give it `aria-label`) · `ivn-btn-block` |
| Status pill | `ivn-pill` · `ivn-pill-blue` · `-green` · `-orange` · `-red` (grey is the default); always with a word, never colour alone |
| Table | `ivn-table-wrap` · `ivn-table` · `ivn-num` |
| List + filter bar | `ivn-filter-bar` · `ivn-chip[aria-pressed]` · `ivn-list` · `ivn-list-row` · `ivn-list-main` · `ivn-list-title` · `ivn-list-sub` · `ivn-list-meta` · `ivn-list-foot` |
| Empty · error | `ivn-empty` · `ivn-error-state` (`role="alert"`) · `ivn-banner` |
| Dialog | `<dialog class="ivn-dialog">` with `ivn-dialog-head` · `-title` · `-body` · `-foot`; open with `data-ivn-open="id"` or `ivnKit.openDialog(el)`, close with `data-ivn-close="value"`, Esc or a click outside |
| Toast | `ivnKit.toast("Saved", {kind: "success" \| "error", timeout: 4000})` — text only |
| Till sheet | `ivn-sheet` · `ivn-sheet-grab` · `ivn-sheet-head` · `ivn-sheet-body` · `ivn-sheet-foot` (≤ 480px) |

`templates/` holds one working page per placement: `desk_page.html`, `till_sheet.html`, `portal.html` (open each with `?theme=dark` or `?dir=rtl`). `templates/sample-theme.js` stands in for the context's `theme` field.

## 7. What the kit does not do

- No fonts, no icon set, no images: nothing is downloaded.
- No network calls, no state, no data binding, no form validation logic (it styles the error state; your code decides it).
- No sorting, paging or virtual scrolling for tables; no date picker beyond the browser's own; no charts.
- No header, rail or till chrome: those are ours and sit around your page.
- No promise of pixel-identical Desk screens: it matches Desk's palette, type scale, corners and control shapes.

## 8. Files

`ivn-kit.css` · `ivn-kit.js` · `templates/` · `tools/check_kit.sh` (the exit check) · `tools/check_page.py` (the page checks it runs) · `tools/test_page_checks.sh` (proves each page check can fail) · `tools/contrast.py` · `tools/test_kit_js.html` (behaviour test) · `tools/render_templates.sh` + `tools/frame.html` (screenshots).

## Technical notes

> **Source of the token values** (a copy that must stay current with its source): design-system repo `iVendNext_PWA`, path `design_system/foundations/` (`00-tokens-desk.html` for light, `00-tokens-pos-dark.html` for dark, `00-tokens-pos.html` for the sample till theme), SHA `05bb4dab92f294edac7b9d5bbac697d3072a4978`. **A defect here is a defect there — send it with the [Kit defect](../../feedback/kit_defect.md) form; we pass it on to the design system's owners.** Values the design system does not hold are marked `kit` in `ivn-kit.css`.

> **The page checks** (`tools/check_page.py`, run by `check_kit.sh` on every page it is given; the default is the three templates). *Proven:* `tools/test_page_checks.sh` builds three pages that are right (one with a dark-only look, a primary button styled in two rules, a part kept left-to-right on purpose) and fourteen planted ones — a stale copy of the kit, no kit stylesheet, a link to a missing file, a remote address, a commented-out link, a text colour under 4.5:1 in light and one only in dark, the same in a single-quoted `style`, a token that does not exist, a margin and a float set to the left, an icon margin set to the right on an inline element, text pinned right, content wider than the window — and requires each right page to pass and each planted one to fail with its own reason (a crash does not count as a refusal). *Not proven or not covered:* contrast reads only a text colour and a background set together in one rule or one `style`, so the pairs inside the kit's classes (`contrast.py` reads those), a colour set alone, a colour reached through another variable of your own, and a tenant's theme overrides are not read, and the three templates set no colour of their own, so their pass on contrast reads no pair; the right-to-left check compares block boxes and every element's margins and paddings between the two drawings and skips the insides of an icon and anything under `dir="ltr"`; it reads one window size (set `IVN_PAGE_SIZE`); a screen review by eye is not done by the script.
