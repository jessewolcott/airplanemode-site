# index.html, the homepage

English `index.html` is the hand-edited source; the six translated pages (`es/` ... `vi/`) are
generated from it (see [i18n.md](i18n.md)), so everything below applies to all seven. No
framework, no external requests except the links themselves (no web fonts, no CDN scripts).
CSS is shared in `assets/site.css`, the config tool is a `<template id="tool-tpl">` in the
page, the strings the script writes are a JSON block `<script type="application/json"
id="ui-strings">`, and all behaviour is one IIFE in `assets/site.js`, loaded at the end of
`<body>`. Line numbers are left out on purpose: search for the ids. Dark only (`<meta name="color-scheme"
content="dark">`, `theme-color #0d0f12`).

## Look

Design tokens on `:root` (top of `assets/site.css`): background `--bg #0d0f12`, panels
`--panel #14171c` / `--panel2 #1a1e24`, lines `--line #252a32` / `--line2 #323843`, text
`--ink #e4dfd3`, `--dim #8f8c84`, **accent `--accent #f2b34b`** (amber) with
`--accent-ink #1a1408`, `--good #7bc47f`, warning callout colours. System font stack
(`--sans`) and a system monospace stack (`--mono`). These deliberately match the box's own
landing page (`../airplanemode/portal/index.html`); keep them in step.

## Page structure

| Part | Lines | Notes |
|---|---|---|
| `<head>` meta | | title, description, canonical + `hreflang` alternates for all 7 languages and x-default, favicon `assets/icon.svg`, apple-touch icon, Open Graph title/description/image (`assets/landing-online.png`, relative) |
| sticky header | | brand (icon + "Airplane**Mode**"), nav: Features, Set up, Apps (Features/Apps hidden <=560px via `.hide-sm`), GitHub (hidden <=440px), language switcher (`details.langs`, see i18n.md) |
| `#lang-hint` | | hidden bar the script shows when the browser prefers another language we have |
| hero | `57-73` | eyebrow, h1, lead, buttons (`#setup`, GitHub), "Early days" note, three phone screenshots (`landing-signin`, `landing-online`, `guide-ask`), decorative (`aria-hidden`) |
| `#features` | `75-113` | six feature cards with inline SVG icons |
| `#setup` | `115-237` | device tabs, progress bar, two guides (R6S, GL.iNet) |
| `#apps` | `239-287` | cards linking to the ten app repos, mirroring the platform's `portal/apps.json` (names, descriptions, icons in `assets/icons/`) |
| footer | `290-295` | links: platform, `docs/hardware.md`, `install.sh` (relative), this repo |
| `<template id="tool-tpl">` | `298-333` | the config tool |
| `#ui-strings` | `336-357` | the page's UI strings as JSON (translated per language, see i18n.md) |
| script | `358` | `<script src="assets/site.js">`: everything interactive (shared by all languages) |

`assets/drop.png` and `assets/admin-vpn-devices.png` exist but are not referenced by the
page today.

## Setup guides (markup)

Each guide is `<div class="guide" data-device="...">` with `role="tabpanel"`, containing an
`<ol class="steps">` of `<li data-step="...">`. Each step has a `.step-head` (h3 + a "done"
checkbox in `label.check`) and a `.step-body`.

NanoPi R6S (`guide-r6s`), step ids:
`r6s-parts` (parts table), `r6s-flash` (FriendlyWrt eflasher image with `docker` in the
name, balenaEtcher or Win32 Disk Imager, SYS LED states drawn with CSS-animated dots),
`r6s-login` (LAN/WAN cabling, `http://192.168.2.1`, root/`password` or empty, set root
password), `r6s-adapters` (ACM in the USB 3.0 port, two radios in LuCI), `r6s-install`
(ssh + the tool), `r6s-done` (open the admin panel, name the hotspot).

GL.iNet (`guide-glinet`, `hidden` by default), with an "untested on a
GL.iNet" callout. Step ids: `gl-model` (arm64, 1 GB RAM, 8 GB+ USB/SD), `gl-ssh`
(`http://192.168.8.1`, ssh), `gl-docker` (static command block `opkg update && opkg install
dockerd docker docker-compose`, `data_root` in `/etc/config/dockerd`), `gl-install` (the
tool), `gl-done` (admin panel; use either GL.iNet's repeater page or AirplaneMode's
Internet source panel, not both).

Each install step contains an empty `<div class="tool-slot">`; the single tool instance is
moved into the selected guide's slot.

## Script (assets/site.js)

### Constants and helpers (site.js:8-29)
- `FALLBACK_URL` = `https://raw.githubusercontent.com/jessewolcott/airplanemode-site/main/install.sh`.
- `installUrl`, see next section. `T` = the parsed `#ui-strings` JSON (the page's own language).
- `LANG` = `<html lang>`. `DEVICES`: `nanopi-r6s` and `glinet`, each with `label` and `profile`
  from `T` (English: "NanoPi R6S · full profile" / "NanoPi R6S (full)", "GL.iNet · lite
  profile" / "GL.iNet (lite)") and default ip `192.168.2.1` / `192.168.8.1`.
- `store.get/set`: JSON in `localStorage` under the prefix `am.`, every access in
  `try/catch` so a blocked or missing storage just falls back to defaults.
- `$`, `$$` (querySelector/All as array), `esc` (HTML-escapes `& < > "`), `fmt(s, vars)`
  (escapes a UI string, then fills `{name}` placeholders with already-escaped HTML).

### How the install URL is derived

```js
const SITE_ROOT = new URL("..", document.currentScript.src);   // the folder above assets/
const installUrl = SITE_ROOT.protocol === "https:" ? new URL("install.sh", SITE_ROOT).href : FALLBACK_URL;
```

- Served over **https**: the site root is the folder above `assets/site.js`, so
  `https://airplanemode.xin/` and `https://airplanemode.xin/ja/` both give
  `https://airplanemode.xin/install.sh` (deriving it from the page URL, as the page did
  before the translations, would give `/ja/install.sh`, which doesn't exist). It still works
  if the whole site moves under a sub-path.
- Anything else (local preview over `http://localhost:8091`, `file://`, any plain-http
  host): the raw GitHub URL. Plain-http origins are deliberately never used, since the
  command pipes the download into a root shell.

This is why moving the site to its own server needs no JS change (hosting.md).

The other two links to the script, "read the script" in the tool and the footer, are plain
relative `href="install.sh"` (`../install.sh` in the translated pages); they don't use
`installUrl`.

### The config tool

Template `#tool-tpl` is cloned once. Fields:

| Key | Element | Meaning | Default |
|---|---|---|---|
| `lan` | `#t-lan` text, `inputmode=decimal` | router LAN address | empty ("detected automatically") |
| `vpn` | `#t-vpn` checkbox | Home VPN support (WireGuard) | checked |
| `rebind` | `#t-rebind` checkbox | "Make hotel sign-in pages work" = rebind protection **off** | checked |
| `wan` | `#t-wan` text, in "Advanced" `<details>` | wired WAN interface name | empty (placeholder `wan`) |
| `dir` | `#t-dir` text, in "Advanced" | install folder | empty (placeholder `/opt/airplanemode`) |

Saved values from `am.opts` are restored into the fields at startup.

Validators: `ipOk` strict dotted quad with each octet 0-255; `nameOk`
`[A-Za-z0-9_.-]+`; `dirOk` absolute path of `[A-Za-z0-9_./-]`. Invalid input gets
`aria-invalid="true"` (red border via CSS) and is simply left out of the command, so the
command is always safe to paste (no shell metacharacters can get in).

`render()` builds the option list in this order:

1. `--device <device>` always (detection works on both, but the command should document
   itself).
2. `--lan-ip <lan>` if non-empty and valid.
3. `--no-wireguard` if VPN unchecked.
4. `--keep-rebind` if the rebind box is **unchecked** (note the inversion: the box is phrased
   as "make sign-in pages work").
5. `--wan <wan>` if valid and not `wan`.
6. `--dir <dir>` if valid and not `/opt/airplanemode`.

`--branch` exists in `install.sh` but is not offered in the tool.

The command is two lines:

```
command -v curl >/dev/null || { opkg update && opkg install curl || apk add -U curl; } >/dev/null 2>&1
curl -fsSL <installUrl> | sh -s -- --device nanopi-r6s [more options]
```

Line 1 installs curl if missing (opkg on 24.10, apk on 25.x) because OpenWrt's wget can't do
TLS with GitHub (installer.md). The plain text goes into `data-copy` on the `<pre>`; the
visible HTML adds a green non-selectable `# ` prompt (`.p`, `user-select: none`), dims line 1
(`.d`) and colours option names amber (`.o`). Everything interpolated goes through `esc`.

`render()` also:
- sets the tool header to the device label (`T["device.<id>"]`);
- fills the "What it does" list (`.t-does`) with eight bullets from `T["does.*"]` (`fmt`
  escapes the string, then fills `{dir}`, `{profile}`, `{user}`, `{name}`, `{ip}` with
  already-escaped HTML), that reflect the options
  (install dir, profile name, `airplane.mode` -> IP, rebind on/off, WireGuard yes/no,
  "and the language model" only on R6S);
- rewrites every `code.ssh` inside the selected guide to `ssh root@<ip>`, where ip is the
  valid typed LAN address or the device default;
- saves all field values to `am.opts`.

Every field fires `render` on `input`.

### Device tabs

`selectDevice(d)`: stores `am.device`, sets `aria-selected` on the two `.device` buttons,
hides the other guide (`hidden`), **moves** the tool node into
`.guide[data-device=d] .tool-slot` with `append` (one instance, so ids like `#t-lan` stay
unique and field state carries across devices), then `render()` and `progress()`. Buttons
have `role="tab"`; the container has `role="tablist"` and handles ArrowLeft/ArrowRight to
cycle and focus. On load, `am.device` is used if it's a known key, else `nanopi-r6s`
and `selectDevice(device)` runs last.

### Step checklist

- `done` is a `Set` of step ids loaded from `am.done` (shared across both guides; step ids
  are prefixed `r6s-`/`gl-` so they don't collide).
- Each checkbox: initial state from the set, toggles `li.done` (number becomes a green
  check via `::before`, body fades to 55% opacity), saves `am.done`, updates progress.
- `progress()` counts done steps in the **selected** guide only and sets `#progText`
  (`T.progress`, "{n} of {total} done") and the width of `#progBar`.
- `#reset` clears the set, storage and every checkbox.

localStorage keys in use: `am.device`, `am.opts`, `am.done` (shared by all languages: step
ids and options are the same on every page, so progress carries over when switching), plus
`am.lang` (a language the visitor picked) and `am.langHint` (hint dismissed). Renaming a step id orphans its
saved state (harmless).

### Copy buttons

One delegated click handler for every `.copy` button (the tool's and the static GL.iNet
docker command). Text = `pre.dataset.copy` if set, else the `<pre>`'s textContent with a
leading `#` + whitespace removed from each line (`/^#\s*/gm`). Tries
`navigator.clipboard.writeText` (needs a secure context: https or localhost); on failure
selects the `<pre>` and uses `document.execCommand("copy")`. The button shows "Copied" in
green for 1.6 s (`T.copied`, then back to `T.copy`).

## Responsive details

Max content width 1040px with a 16px gutter (`.wrap`). `body { overflow-x: clip }` stops the
rotated phone screenshots from causing horizontal scroll. Breakpoints:

| Width | Change |
|---|---|
| <=860px | hero becomes one column; phones area 380px tall, screenshots 170px |
| <=640px | tool fields one column |
| <=600px | device tabs stack |
| <=560px | Features/Apps nav links hidden; step indent 44px with smaller circles; the tool gets `margin-left: -44px` to use the full width under the step number; command `<pre>` gets 46px top padding so the Copy button sits above the text |
| <=520px | parts table rows become stacked blocks |
| <=420px | phones 320px tall, screenshots 140px |

Also: `scroll-padding-top: 72px` so anchors land below the sticky header; long code wraps
(`overflow-wrap: anywhere`, `pre-wrap`); `prefers-reduced-motion` stops the LED blink and
smooth scrolling.

## Things that are static on purpose (or not yet dynamic)

- The admin links (`a.admin-link`) always point at
  `http://airplane.mode:8080/admin/`; nothing in the script updates them, even though they
  carry a class.
- The device default IPs are duplicated: `DEVICES` in the script, the LuCI/admin links in
  the guide text, and the `LAN_IP` defaults in the platform's hardware profiles.
- The R6S step texts follow FriendlyElec's NanoPi R6S wiki; none of it has been tried on a
  real board.
