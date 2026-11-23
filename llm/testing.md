# Testing

There is no browser test for the page. CI tests `install.sh` (job `installer`) and that the
translated pages are in step with English (job `i18n`, `tools/check_i18n.py`, rules in
[i18n.md](i18n.md)).

## CI: `.github/workflows/check.yml`

Runs on every push and pull request, one job `installer` on `ubuntu-latest`:

1. `actions/checkout@v7`.
2. **shellcheck**: `shellcheck -s sh -e SC2046,SC2086 install.sh tests/openwrt-run.sh`.
   `-s sh` checks as POSIX sh (no bashisms). SC2046/SC2086 (unquoted `$(...)` / `$var`) are
   excluded because the scripts rely on word splitting in a few places, e.g.
   `set -- $(uci -q get network.lan.ipaddr)` in `detect_lan_ip`.
3. `docker/setup-qemu-action@v3` registers qemu binfmt so an arm64 image runs on the x86
   runner.
4. Runs the installer in OpenWrt:

```sh
docker run --rm --platform linux/aarch64_generic -v "$PWD:/src:ro" \
  -v "$PWD/tests/docker-stub:/usr/bin/docker:ro" \
  openwrt/rootfs:aarch64_generic-24.10.4 sh /src/tests/openwrt-run.sh
```

- `openwrt/rootfs:aarch64_generic-24.10.4` is the official OpenWrt 24.10.4 root filesystem
  for generic arm64: real busybox ash, real `uci`, opkg, uclient-fetch, rpcd/uhttpd
  binaries. `uname -m` is `aarch64` under qemu, so the arch check passes for real.
- The repo is mounted read-only at `/src`.
- `tests/docker-stub` is mounted over `/usr/bin/docker`, so no Docker-in-Docker is needed.

## tests/docker-stub

```sh
echo "docker $*" >>/tmp/docker.log
case "$*" in
  "info -f"*) echo /opt/docker ;;          # DockerRootDir for the free-space check
  "version -f"*) echo 27.0.0 ;;            # printed in "Docker 27.0.0 with compose"
  "compose exec"*) exit 1 ;;               # router-API probe (and update.sh health waits) fail
  "compose config --services") echo proxy; echo admin ;;   # no llm/guide services
esac
exit 0
```

Everything else (`docker info`, `docker compose version`, `compose pull`, `compose up`,
`compose ps`, `image prune`) succeeds silently. Effects:
- preflight's Docker checks pass;
- `update.sh` "starts" the stack and skips the model and Wikivoyage waits (no `llm` or
  `guide` in the service list), so it doesn't loop for 10-20 minutes;
- `compose ps --services` prints nothing, so router-setup.sh doesn't restart admin;
- the router-API probe fails for both URLs, so the installer takes the warning path and
  `ROUTER_URL` is not changed.

Every call is logged to `/tmp/docker.log` inside the container (useful when debugging; not
asserted).

## tests/openwrt-run.sh

Setup (`tests/openwrt-run.sh:9-14`):
- `mkdir -p /var/lock /var/run /opt/docker` (uci locks, pid files, the stub's DockerRootDir).
- Writes a minimal `/etc/config/network` like a fresh FriendlyWrt: `interface lan` with
  `list ipaddr 10.9.8.1/24` (list + CIDR, the hardest shape for `detect_lan_ip`) and
  `interface wan` with `proto dhcp`.
- `/etc/config/dhcp` with one `config dnsmasq`.
- Empty `/etc/config/rpcd`.
- No `/etc/config/wireless`, so the radio check warns "no Wi-Fi radios yet".

Assertions, in order:

1. `sh /src/install.sh --no-wireguard` must **fail** and its output must contain "couldn't
   tell which device" (the container has no board name, device-tree model or
   `/etc/glversion`).
2. `sh /src/install.sh --device nanopi-r6s --no-wireguard` must succeed (`set -eu`), then:
   - `.env` has exactly `LAN_IP=10.9.8.1` (read from uci, CIDR stripped, overriding the
     profile's `192.168.2.1`);
   - `ROUTER_USER=airplanemode` (router-setup.sh created the restricted login);
   - `ADMIN_PASSWORD=` followed by exactly 16 characters (update.sh generated it);
   - `uci get network.wan.metric` is `10` (Ethernet first);
   - `dhcp.@dnsmasq[0].address` contains `/airplane.mode/10.9.8.1`.
3. Re-run with the same flags: output contains "keeping the existing .env", and the
   `ADMIN_PASSWORD` line is unchanged.
4. Prints `PASS`.

`--no-wireguard` keeps the test from installing WireGuard packages.

## What it covers and what it doesn't

Covered for real: busybox-ash compatibility end to end, option parsing, root/uci/arch
checks, device-detection failure, curl bootstrap and the TLS path to GitHub (the image's
`curl`/`git` are installed through opkg if missing), the **real `git clone` of the platform
repo's `main` branch**, `.env` creation and `set_env`, LAN detection from a list+CIDR value,
the platform's `router-setup.sh` against real uci/rpcd config files, `update.sh`'s password
step, the summary, and re-run idempotency.

Not covered:
- anything Docker actually does (pulling, starting, health), and the success path of the
  router-API probe or its LAN fallback (the stub always fails `compose exec`);
- the R6S/GL.iNet detection success paths (no real sysinfo in the container);
- the tarball fallback (git is available);
- apk-based OpenWrt (25.x / FriendlyWrt 25.12);
- real FriendlyWrt or GL.iNet firmware, real Wi-Fi radios, real hardware. All *untested*.
- service restarts: in an unprivileged OpenWrt container netifd/procd don't really run,
  and router-setup.sh's 60 s timeouts cover hangs (platform CLAUDE.md gotcha).

Dependencies to be aware of: the test needs internet (opkg feeds, github.com) and clones the
platform's **current `main`**, so a breaking change in `../airplanemode/scripts/*.sh` or the
hardware profiles can make this repo's CI fail with no change here. The `--branch` option is
not exercised.

## Running it locally

From the repo root, with Docker Desktop (arm64 emulation is built in):

```sh
docker run --rm --platform linux/aarch64_generic -v "$PWD:/src:ro" \
  -v "$PWD/tests/docker-stub:/usr/bin/docker:ro" \
  openwrt/rootfs:aarch64_generic-24.10.4 sh /src/tests/openwrt-run.sh
```

On Windows Git Bash, `$PWD` may need `MSYS_NO_PATHCONV=1` or a Windows-style path for the
bind mount. Line endings: `.gitattributes` forces LF on `*.sh` and `tests/docker-stub`; with
CRLF the scripts would fail under ash.

Shellcheck locally: `shellcheck -s sh -e SC2046,SC2086 install.sh tests/openwrt-run.sh`.

Translation check: `python tools/check_i18n.py` (also compares the English app cards with
`../airplanemode/portal/apps.json` when that sibling repo is there).

Manual page check: `python -m http.server 8091` and open `http://localhost:8091` (port 8000
is reserved by Windows on the dev machine). Over http the command uses the raw GitHub URL.
