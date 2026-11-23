<p align="center"><img src="assets/icon.svg" width="96" alt="AirplaneMode icon"></p>

# airplanemode-site

The public homepage and one-line installer for [AirplaneMode](https://github.com/jessewolcott/airplanemode).
Live at **https://airplanemode.xin** (GitHub Pages with its own domain, platform decision
0019). CI publishes it on every push to `main` that passes the installer checks.

| File | What it is |
|---|---|
| `index.html` | the homepage (English, the source): features, apps, and a step-by-step setup guide per device (NanoPi R6S, GL.iNet) with a config tool that builds your install command |
| `es/` `fr/` `it/` `zh/` `ja/` `vi/` | the translated homepages, generated from `index.html` + `i18n/<lang>.json` by `tools/build_i18n.py` (don't edit them) |
| `assets/site.css`, `assets/site.js` | the style and behaviour every language's page shares |
| `i18n/`, `tools/` | translations, the allowlist of names that stay English, the generator and the check |
| `install.sh` | the installer the command runs on the router |
| `assets/` | icon and screenshots (copied from the platform repo's `portal/` and `docs/screenshots/`) |
| `tests/` | runs the installer inside an OpenWrt 24.10 arm64 container with a stub Docker (CI) |

## The installer

On the router, as root, while it's online:

```sh
command -v curl >/dev/null || { opkg update && opkg install curl || apk add -U curl; } >/dev/null 2>&1
curl -fsSL https://airplanemode.xin/install.sh | sh
```

It checks the router (OpenWrt, arm64, Docker with compose, online, free space, Wi-Fi radios),
clones the platform repo to `/opt/airplanemode`, copies the device's hardware profile to
`.env` with the router's real LAN address, then runs the platform's own
`scripts/router-setup.sh` and `scripts/update.sh`. Finally it checks that the admin service
can log in to the router's API, falls back to `http://<LAN_IP>/ubus` if the Docker gateway
is blocked, and prints the addresses and the admin password. Running it again updates the
install and keeps `.env`.

Options (`sh -s -- --help`): `--device nanopi-r6s|glinet`, `--lan-ip`, `--wan`,
`--keep-rebind`, `--no-wireguard`, `--dir`, `--branch`.

**Why curl and not wget:** OpenWrt's built-in `wget` (uclient-fetch with libustream-mbedtls,
24.10) fails the TLS handshake with GitHub's servers (`github.com`, `codeload`, `*.github.io`),
while `curl` on the same mbedTLS works. Found while testing in the `openwrt/rootfs` containers.

The installer is a thin wrapper: router logic stays in the platform repo's scripts, so
there's one place to change it.

## Develop

Changing the homepage: change English `index.html`, update all six translations in
`i18n/<lang>.json` (`python tools/build_i18n.py --sync-keys` adds new strings as null), run
`python tools/build_i18n.py` and `python tools/check_i18n.py`. CI fails if they don't match.

```sh
python -m http.server 8091      # then http://localhost:8091 (port 8000 is reserved on Windows)
```

Test the installer like CI does (needs Docker; arm64 emulation comes with Docker Desktop):

```sh
docker run --rm --platform linux/aarch64_generic -v "$PWD:/src:ro" \
  -v "$PWD/tests/docker-stub:/usr/bin/docker:ro" \
  openwrt/rootfs:aarch64_generic-24.10.4 sh /src/tests/openwrt-run.sh
```

The setup steps for FriendlyWrt come from FriendlyElec's
[NanoPi R6S wiki](https://wiki.friendlyelec.com/wiki/index.php/NanoPi_R6S). None of this has
been run on real hardware yet.
