# airplanemode-site: how it's built

Checked-in reference for LLMs and engineers who open this repo cold. The Pages deploy
stages only the site's own files, so these notes aren't served on airplanemode.xin. Written 2026-11-22 against the code at
that date; if the code and these notes disagree, the code wins.

## Overview

`airplanemode-site` is the public front of the AirplaneMode travel-router project: one
static homepage in seven languages (English `index.html` is the source; `es/ fr/ it/ zh/
ja/ vi/` are generated from it by `tools/build_i18n.py`; shared `assets/site.css` and
`assets/site.js`, images in `assets/`) and a
one-line installer (`install.sh`) that a user pipes into `sh` on the router. The page sells
the project, walks a user through setting up a NanoPi R6S or a GL.iNet router step by step,
and builds the exact install command with a small config tool. The installer is a **thin
POSIX-sh wrapper** that runs under OpenWrt's busybox ash: it checks the router, fetches the
platform repo (`jessewolcott/airplanemode`) to `/opt/airplanemode`, writes `.env` from the
device's hardware profile, then hands off to the platform's own `scripts/router-setup.sh`
and `scripts/update.sh`, probes the router API and prints the admin password. **The site is
live at https://airplanemode.xin** (GitHub Pages with its own domain, decision 0019, which
superseded 0012), and the install command fetches `https://airplanemode.xin/install.sh`. CI runs shellcheck and the installer inside a real OpenWrt 24.10 arm64 rootfs
(qemu) with a stub `docker`. Nothing has been run on real hardware.

## Files in this folder

| File | What it covers |
|---|---|
| [installer.md](installer.md) | `install.sh` function by function: `main()`, options, preflight conditions, device and LAN detection, curl vs wget, git vs tarball, `.env`, the platform scripts, the router-API probe, the summary |
| [i18n.md](i18n.md) | the translations: how the generator finds strings, `i18n/<lang>.json`, the allowlist, the language switcher and hint, the check's rules, how to change the page |
| [page.md](page.md) | `index.html`: layout, device tabs, step checklist (localStorage), the config tool and command builder, install-URL derivation, copy buttons, responsive rules |
| [testing.md](testing.md) | CI (`.github/workflows/check.yml`), `tests/openwrt-run.sh`, `tests/docker-stub`, what is and isn't covered, running it locally |
| [hosting.md](hosting.md) | Hosting history and status, local preview, how to deploy to its own server later and the exact list of things to change then |
| [gotchas.md](gotchas.md) | Sharp edges, known limitations and invariants that are easy to break |

## Repo map

| Path | Role |
|---|---|
| `index.html` | the English homepage, hand-edited, the source of the translations (markup, the tool `<template>`, the `#ui-strings` JSON) |
| `es/` `fr/` `it/` `zh/` `ja/` `vi/` | generated translated pages (`index.html` each); never edit by hand |
| `assets/site.css`, `assets/site.js` | style and behaviour shared by all seven pages |
| `i18n/<lang>.json`, `i18n/allowlist.json` | translations (English text -> translation) and the names/commands that stay English |
| `tools/build_i18n.py`, `tools/check_i18n.py` | the generator and the CI check (stdlib Python) |
| `install.sh` | the installer (292 lines; `main()` at `install.sh:262`, invoked at `install.sh:291-292`) |
| `assets/` | `icon.svg`, `apple-touch-icon.png`, screenshots copied from the platform repo (`portal/`, `docs/screenshots/`) |
| `tests/openwrt-run.sh` | CI test script, runs inside the OpenWrt container |
| `tests/docker-stub` | fake `docker` binary bind-mounted over `/usr/bin/docker` in the test |
| `.github/workflows/check.yml` | CI: shellcheck + the OpenWrt container test, the translation check, then (on `main`) the GitHub Pages deploy |
| `CNAME` | the Pages custom domain, `airplanemode.xin` |
| `.gitattributes` | forces LF for `*.sh` and `tests/docker-stub` (they run on Linux), and for html/css/js/json/py (so the render comparison is byte-exact) |
| `.nojekyll` | leftover from the branch-built Pages period; harmless (the site is built by Actions now) |
| `README.md`, `CLAUDE.md` | human and Claude notes; `CLAUDE.md` holds the working rules |

## Related material outside this repo

- `../airplanemode/scripts/router-setup.sh`, `../airplanemode/scripts/update.sh`: what the
  installer actually delegates to (summarised in installer.md).
- `../airplanemode/hardware/nanopi-r6s.env`, `../airplanemode/hardware/glinet.env`: the
  profiles copied to `.env`.
- `../airplanemode/docs/decisions/0011-install-site.md` (why a separate site + thin
  installer + curl) `0012-site-own-server.md` (Pages off, own server, raw URL meanwhile) and
  `0019-site-on-pages-own-domain.md` (Pages back, under airplanemode.xin).
- `../airplanemode/CLAUDE.md`: platform rules (restricted rpcd login, `uci apply`, etc.).

## Rules worth repeating (from CLAUDE.md)

- `install.sh` stays POSIX sh, busybox-ash compatible, and thin. Router changes go in the
  platform's `router-setup.sh`, not here.
- Option names are shared by the page's config tool and `install.sh`; change both together.
- A new hardware profile needs: `detect_device` + the `--device` check in `install.sh`, and a
  tab + guide in `index.html`.
- Use curl, never OpenWrt's wget, for anything on GitHub.
- Keep the look in step with the box's landing page (`../airplanemode/portal/index.html`,
  dark, amber `#f2b34b`).
- Keep the site on its own domain with Enforce HTTPS on (decision 0019).
- Mark anything not verified on hardware as untested.
- Change the homepage in English, update all six translations, run `tools/build_i18n.py` and
  `tools/check_i18n.py` (CI fails if they don't match).
