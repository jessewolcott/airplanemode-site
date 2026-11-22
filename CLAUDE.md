# airplanemode-site: notes for Claude

Public homepage + one-line installer for AirplaneMode. Served at **https://airplanemode.xin**
by GitHub Pages under its own domain (platform decision 0019, superseding 0012): the `pages`
job in `.github/workflows/check.yml` publishes `index.html`, `install.sh`, `assets/` and `CNAME`
on pushes to `main` that pass the installer checks. The page builds its command from the
address that serves it over https. Keep **Enforce HTTPS** on (`curl | sh`). The old raw GitHub
URL of `install.sh` still works for anyone who copied it, so keep `main`'s copy working.
Platform notes live in `../airplanemode/CLAUDE.md`. Read those first.

- Plain static site: `index.html` (inline CSS/JS, no build), `assets/`, `install.sh`. Keep
  the look in step with the box's landing page (`../airplanemode/portal/index.html`: dark,
  amber `#f2b34b`). Screenshots and icon are copies; refresh them when the platform's change.
- The **apps** section mirrors the platform's `portal/apps.json`: same names, descriptions and
  categories, icons copied into `assets/icons/`, each card linking to the app's repo. When an
  app is added or its description changes there, update the card here too.
- `install.sh` must stay POSIX sh that runs under OpenWrt's busybox ash, and stays a **thin
  wrapper**: router changes belong in the platform's `scripts/router-setup.sh`, not here.
  Everything runs from `main()` at the bottom (a half-downloaded script does nothing).
- Use **curl** for downloads, never OpenWrt's wget: uclient-fetch + mbedTLS can't do TLS
  with GitHub (see README). The page's command installs curl first.
- The page's config tool and `install.sh` share the option names (`--device`, `--lan-ip`,
  `--wan`, `--keep-rebind`, `--no-wireguard`, `--dir`, `--branch`). Change both together.
- If the platform adds a hardware profile (`hardware/<name>.env`), add it to `detect_device`
  and the `--device` check in `install.sh`, plus a tab in `index.html`.
- Test: `tests/openwrt-run.sh` in `openwrt/rootfs:aarch64_generic-24.10.4` with the stub
  Docker (command in README); CI runs it and shellcheck. Local preview: port 8091.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  Push to `main` freely for requested work (it publishes the site).
- Mark anything not verified on real hardware as untested.
