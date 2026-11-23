# install.sh, step by step

`install.sh` (281 lines) is what the one-line command runs on the router, as root, while the
router is online:

```sh
command -v curl >/dev/null || { opkg update && opkg install curl || apk add -U curl; } >/dev/null 2>&1
curl -fsSL https://airplanemode.xin/install.sh | sh -s -- --device nanopi-r6s
```

Constraints it is written under:

- **POSIX sh under OpenWrt's busybox ash.** No bashisms, no `local`, no arrays. CI runs
  `shellcheck -s sh -e SC2046,SC2086` (word splitting on `$(...)`/`$var` is used on purpose,
  e.g. `detect_lan_ip`).
- **Thin wrapper.** All router configuration is done by the platform repo's
  `scripts/router-setup.sh`; the installer only checks, fetches, writes `.env`, calls the
  platform scripts, probes and reports. Decision 0011 is the reason: one place for router
  logic.
- **Idempotent.** Re-running updates the checkout and keeps `.env` (passwords).
- All functions use globals (`DEVICE`, `LAN_IP`, `WAN`, `KEEP_REBIND`, `NO_WG`, `DIR`,
  `BRANCH`, plus scratch names like `info`, `arch`, `root`, `free`, `url`, `alt`).

## Layout of the file

| Lines | Part |
|---|---|
| `1-14` | header comment: usage, options pointer, why curl, re-run safety, why `main()` |
| `16-17` | `REPO` (git URL of the platform) and `TARBALL` (codeload base for branch snapshots) |
| `19-22` | output helpers `say` (yellow `==>`), `ok` (green check), `warn` (yellow `!`), `die` (red "Stopped:" to stderr, `exit 1`) |
| `24-37` | `usage()` (heredoc; note it also prints the raw GitHub URL) |
| `39-47` | `pkg_install` |
| `49-56` | `fetch` |
| `58-61` | `ensure_curl` |
| `63-71` | `set_env` / `get_env` |
| `73-81` | `detect_device` |
| `83-88` | `detect_lan_ip` |
| `90-95` | `valid_ip` |
| `97-152` | `preflight` |
| `154-173` | `fetch_code` |
| `175-198` | `configure` |
| `200-204` | `setup_router` |
| `206-209` | `start_stack` |
| `211-238` | `check_router_api` |
| `240-249` | `finish` |
| `251-278` | `main` |
| `280-281` | `set -eu` then `main "$@"` |

## Why everything runs from main()

The file only defines functions until the last two lines (`install.sh:291-292`):

```sh
set -eu
main "$@"
```

With `curl ... | sh`, the shell executes the script as it streams in. If the connection
drops halfway, a script with top-level commands could run a partial sequence (for example
copy a profile but never run setup). Here a truncated download only defines some functions
and exits without calling anything, because the call is the very last line. `set -eu` is
also placed there so it applies to the whole run: any unhandled failing command or unset
variable stops the installer.

Arguments reach `main` because of `sh -s -- [options]`: `-s` reads the script from stdin and
everything after `--` becomes `$@`.

## Option parsing (`main`, install.sh:262-289)

Defaults: `DEVICE=""`, `LAN_IP=""`, `WAN=""`, `KEEP_REBIND=0`, `NO_WG=0`,
`DIR=/opt/airplanemode`, `BRANCH=main`.

| Option | Effect |
|---|---|
| `--device NAME` | `DEVICE=NAME` (validated later in preflight: `nanopi-r6s` or `glinet`) |
| `--lan-ip ADDR` | `LAN_IP=ADDR` (validated in `configure` with `valid_ip`) |
| `--wan NAME` | `WAN=NAME` (checked in `configure`: `uci -q get network.NAME` must succeed) |
| `--keep-rebind` | `KEEP_REBIND=1` (passed as `KEEP_REBIND_PROTECTION` to router-setup.sh) |
| `--no-wireguard` | `NO_WG=1` (passed as `SKIP_WIREGUARD`) |
| `--dir PATH` | `DIR=PATH` |
| `--branch NAME` | `BRANCH=NAME` (platform branch for clone or tarball) |
| `-h`, `--help` | `usage`, `exit 0` |
| anything else | `die "unknown option: $1 (see --help)"` |

Value options read `${2:-}` and do an extra `shift`. After the loop,
`[ -n "$DIR" ] && [ -n "$BRANCH" ] || die "--dir and --branch need a value."` catches
`--dir ""` / `--branch ""`. Only `--` forms exist; there is no `--opt=value` syntax.

Edge: a value option given as the **last** argument with no value (`--device` alone) makes
the loop's second `shift` run with no arguments left. In POSIX shells that is an error, and
with `set -e` the script stops with the shell's own message rather than a friendly one. Not
covered by tests.

Then it prints the banner and runs, in order: `preflight`, `fetch_code`, `configure`,
`setup_router`, `start_stack`, `check_router_api`, `finish`.

## Helpers

### pkg_install (install.sh:39-47)
Prefers **apk** if present (OpenWrt 25.x / FriendlyWrt 25.12), else **opkg** (24.10), else
returns 1. Runs `update` then `add`/`install`, all output discarded. Return status is what
callers test.

### fetch (install.sh:50-56)
Download a URL to stdout. If `curl` exists: `curl -fsSL -m 600 --retry 2 "$1"` (fail on
HTTP errors, silent, follow redirects, 10-minute cap, 2 retries). Otherwise
`wget -q -T 30 -O - "$1"`, which on stock OpenWrt is uclient-fetch and is expected to fail
against GitHub (see below); it is only a last resort.

### ensure_curl (install.sh:58-61)
If `curl` is missing, `pkg_install curl ca-bundle`. On failure it only warns ("trying the
built-in wget"); it does not stop. The page's command already installs curl before the
script is even downloaded, so this matters mostly when someone runs the script another way.

### Why curl and not wget
OpenWrt 24.10's built-in `wget` is **uclient-fetch with libustream-mbedtls**. In testing in
the `openwrt/rootfs` containers it fails the TLS handshake with GitHub's servers
(`github.com`, `codeload.github.com`, `*.github.io`), while **curl linked against the same
mbedTLS works**. So: curl for every download here, and the page's command bootstraps curl
first (`opkg update && opkg install curl || apk add -U curl`). Source: README "Why curl",
`install.sh:9-11`, decision 0011.

### set_env / get_env (install.sh:64-71)
- `set_env KEY VALUE`: if `^KEY=` exists in `$DIR/.env`, replace that line with
  `sed -i "s|^KEY=.*|KEY=VALUE|"`; else append `KEY=VALUE`. The `|` delimiter means a value
  containing `|` (or `&`, or `\`) would corrupt the substitution. Values written today are
  an IPv4 address, an interface name and a URL, so it's fine; keep it that way or escape.
- `get_env KEY`: last matching line's value (`tail -n 1 | cut -d= -f2-`), empty if the file
  or key is missing.

### detect_device (install.sh:73-81)
Collects text from three sources, errors ignored:
1. `/tmp/sysinfo/board_name` (OpenWrt's board name, e.g. `friendlyelec,nanopi-r6s`),
2. `/tmp/sysinfo/model`,
3. `/proc/device-tree/model` with NUL bytes stripped (`tr -d '\000'`).

Lower-cases the lot and matches:
- `*nanopi-r6s*` or `*"nanopi r6s"*` -> `nanopi-r6s`
- `*glinet*`, `*gl-*` or `*gl.inet*` -> `glinet`
- otherwise, if `/etc/glversion` exists (GL.iNet firmware marker) -> `glinet`
- otherwise prints nothing.

Always returns 0 (so `set -e` doesn't fire inside `$(...)`). Note `*gl-*` is a broad
pattern: any board string containing `gl-` matches. The R6S check comes first, so an R6S
can't be misread as GL.iNet. *Untested* on real boards: the exact strings come from OpenWrt
conventions, not from a device.

### detect_lan_ip (install.sh:83-88)
`set -- $(uci -q get network.lan.ipaddr || true)` then echoes `${1%%/*}`. Handles the three
shapes OpenWrt uses: `192.168.2.1`, `192.168.2.1/24` (CIDR, newer configs) and a list
(`list ipaddr`, uci prints values space-separated; the first one wins). Unquoted on purpose
for the word splitting. Empty output if the option is missing.

### valid_ip (install.sh:90-98)
Loose IPv4 check: only digits and dots, no `..`, not starting or ending with `.`, exactly
three dots. It does **not** range-check octets (`999.1.1.1` passes). The page's own check
is strict (0-255), so commands built by the page are always in range.

## preflight (install.sh:100-155)

Each check either `die`s (stop) or `warn`s (continue). Exact conditions:

| # | Check | Condition | Result on failure |
|---|---|---|---|
| 1 | root | `[ "$(id -u)" = 0 ]` | die "run this as root (ssh root@<router>)." |
| 2 | OpenWrt | `command -v uci` | die "this doesn't look like OpenWrt (no uci command)." |
| 3 | arm64 | `uname -m` is exactly `aarch64` | die "AirplaneMode's images are arm64 only; this router is $arch." |
| 4 | device | if `--device` not given, `detect_device`; empty -> die "couldn't tell which device this is. Add --device nanopi-r6s or --device glinet." Then `case` allows only `nanopi-r6s`/`glinet` | die "unknown device '...'" |
| 5 | docker binary | `command -v docker` | die with a device-specific hint: R6S -> flash the FriendlyWrt image with `docker` in its name; GL.iNet -> install dockerd, docker, docker-compose on USB/SD |
| 6 | docker daemon | `docker info` succeeds | die "Docker is installed but not running. Try: /etc/init.d/dockerd start" |
| 7 | compose v2 | `docker compose version` succeeds | die "Docker is missing the 'compose' plugin. Install docker-compose (v2)." |
| - | | prints `Docker <docker version -f '{{.Server.Version}}'> with compose` | |
| 8 | curl | `ensure_curl` | warn only |
| 9 | online | `fetch https://github.com` succeeds | die "the router can't reach github.com. Get it online first (Ethernet into WAN, or join a Wi-Fi in LuCI)." |
| 10 | free space | need 5,000,000 KB (R6S, the model is ~3.1 GB) or 1,200,000 KB (GL.iNet), "images + model + Wikivoyage". Path = `docker info -f '{{.DockerRootDir}}'`, falling back to `/` if that isn't a directory. Free = 4th column of `df -k` line 2 | **warn only**: non-numeric -> "couldn't check free space; about N MB is needed"; below need -> "only X MB free ... about N MB is needed"; else ok |
| 11 | Wi-Fi radios | count of `=wifi-device$` lines in `uci -q show wireless` | **warn only**: >=2 ok; 1 -> "works, but two adapters ... are faster"; 0 -> "Plug in the USB Wi-Fi adapters; the admin panel picks them up later." |

Order matters: Docker is checked before the network, so a router without Docker fails fast
without any download. The online check is done with `fetch`, so it also proves the TLS path
the later downloads will use. Free space and radios never block, because the user may fix
them later (more storage, adapters plugged in after install).

Note `df -k` line 2: if the filesystem name is long, some `df` implementations wrap the
line and the 4th field of line 2 is wrong or empty; the non-numeric branch then just warns.

## fetch_code (install.sh:157-184)

1. If `$DIR/.git` exists: `git -C "$DIR" pull --ff-only -q`. Success -> "updated"; failure
   -> warn "couldn't update; using the copy already there". Return. (Note: it pulls whatever
   branch is checked out; `--branch` is ignored on updates.)
2. If `$DIR` exists and is non-empty (and has no `.git`): die "$DIR exists and isn't an
   AirplaneMode checkout. Move it or use --dir." A previous **tarball** install lands here
   too, see below.
3. If `git` is missing: `pkg_install git git-http` (git-http gives https remotes on
   OpenWrt). Failure only warns.
4. `mkdir -p "$(dirname "$DIR")"`, then `git clone -q -b "$BRANCH" "$REPO" "$DIR"` if git
   exists.
5. If git is absent or the clone failed: tarball fallback. `mkdir -p "$DIR"` and
   `fetch "$TARBALL/$BRANCH" | tar -xz -C "$DIR" --strip-components=1` (codeload URL
   `https://codeload.github.com/jessewolcott/airplanemode/tar.gz/refs/heads/<branch>`).
   Failure -> die "download failed." Success says re-run the installer to update later,
   because `update.sh`'s `git pull` can't work without `.git` (it only warns there).

Tarball re-runs: a snapshot install has a non-empty `$DIR` without `.git`, so step 2 stops a
re-run with "isn't an AirplaneMode checkout". The success message's "re-run this installer
to update later" therefore only holds once git is installable. Worth knowing before relying
on the snapshot path; it isn't exercised by CI (the test image gets git).

## configure (install.sh:186-209)

1. `.env`: if `$DIR/.env` exists, keep it ("your passwords stay the same"). Otherwise
   `cp "$DIR/hardware/$DEVICE.env" "$DIR/.env"` and `chmod 600`. The profile carries
   `COMPOSE_PROFILES` (`llm` on R6S, empty on GL.iNet), `HTTP_PORT=8080`, a default
   `LAN_IP` (R6S `192.168.2.1`, GL.iNet `192.168.8.1`), memory limits, Drop limits,
   `ROUTER_BACKEND=openwrt` and `ROUTER_URL=http://host.docker.internal/ubus`. On an existing
   install the device flag does not swap profiles.
2. LAN IP: `--lan-ip` if given, else `detect_lan_ip`. If non-empty: `valid_ip` or die
   "'X' isn't an IPv4 address.", then `set_env LAN_IP`. If empty: warn and keep the
   profile's value. This runs on every run, including re-runs, so `.env` follows the
   router's real LAN address.
3. WAN: only if `--wan` given. `uci -q get "network.$WAN"` must succeed, else die "there's
   no network interface called 'X'."; then `set_env WAN_IFACE`. Without `--wan`,
   router-setup.sh defaults to `wan`.

`LAN_IP` matters because Caddy publishes only on `LAN_IP` and the admin container uses it
as DNS (platform CLAUDE.md), and router-setup.sh points `airplane.mode` at it.

## setup_router (install.sh:211-215)

```sh
( cd "$DIR" && KEEP_REBIND_PROTECTION=$KEEP_REBIND SKIP_WIREGUARD=$NO_WG sh scripts/router-setup.sh ) \
    || die "router setup failed (see above)."
```

Subshell so the `cd` doesn't leak; env vars passed per-command. What the platform script
does (`../airplanemode/scripts/router-setup.sh`), for context:

1. Installs the rpcd ACL `router/rpcd-acl-airplanemode.json` to
   `/usr/share/rpcd/acl.d/airplanemode.json`; creates or updates an rpcd login
   `airplanemode` with a fresh random 24-char password hashed by `uhttpd -m`; read/write
   ACL group `airplanemode`; `uci commit rpcd`.
2. DNS: `dhcp.@dnsmasq[0].rebind_protection=0` unless `KEEP_REBIND_PROTECTION=1`; replaces
   any `/airplane.mode/...` dnsmasq address with `/airplane.mode/$LAN_IP`.
3. `network.$WAN_IFACE.metric=10` (Ethernet beats the Wi-Fi uplink at 20), if the interface
   exists, else a note.
4. WireGuard (`wireguard-tools`, `luci-proto-wireguard`) via apk or opkg unless
   `SKIP_WIREGUARD=1` or already installed; failure only warns.
5. Restarts rpcd, dnsmasq and reloads network, each with a hand-rolled 60 s timeout.
6. Rewrites `ROUTER_USER`/`ROUTER_PASSWORD` in `.env`, `chmod 600`; restarts the admin
   container if it is already running.

It rotates the router password on every run, which is why re-running the installer is
safe and also refreshes the admin service's credentials.

## start_stack (install.sh:217-220)

`( cd "$DIR" && sh scripts/update.sh ) || die "starting the apps failed ..."`. The platform's
`update.sh`: generates `ADMIN_PASSWORD` (16 chars) into `.env` if missing; warns if there is
no router login or it's root; `git pull --ff-only` (warns on failure); `docker compose pull
--ignore-buildable`; `docker compose up -d --build --remove-orphans`; if the `llm` service
exists, waits up to 10 minutes for `http://llm:8080/health` (exits 1 on timeout, which
makes the installer die); if `guide` exists, waits up to 20 minutes for Wikivoyage
(`content_ready`), only warning on timeout; prunes images. "About 3.8 GB on the R6S the first time"
is the message the installer prints (much less on GL.iNet, which has no model).

## check_router_api (install.sh:224-249)

Verifies the admin service can log in to ubus as the restricted user, from inside the admin
container (that is the network path that matters).

- `probe` is an inline Python program run with `docker compose exec -T admin python -c
  "$probe" "$url"`. It POSTs a JSON-RPC `call` to `session login` with the null session id
  `000...0` and `ROUTER_USER`/`ROUTER_PASSWORD` from the container's environment, timeout
  8 s. Exit 0 if `result[0] == 0` (ubus OK), 2 if the router answered but refused, 1 on any
  exception (unreachable, bad JSON). The installer treats any non-zero as failure.
- `cd "$DIR"` (no subshell; it's late in the run, nothing depends on the old cwd).
- First URL: `ROUTER_URL` from `.env`, default `http://host.docker.internal/ubus` (the
  Docker host gateway, i.e. the router itself). Success -> ok, return.
- Fallback: `http://<LAN_IP>/ubus` (from `.env`), tried only if different from the first.
  Success -> `set_env ROUTER_URL <alt>`, `docker compose up -d admin` (recreates the
  container so it picks up the new env), ok "(saved to .env)". Rationale: some firewalls
  block input from the Docker bridge to the gateway address but allow the LAN address.
- Both fail -> two warnings: in LuCI, Network -> Firewall, allow input from the `docker`
  zone, then re-run. It does **not** die; status pages work without router control.

## finish (install.sh:251-260)

Reads `LAN_IP`, `HTTP_PORT` (default 8080) and `ADMIN_PASSWORD` from `.env` and prints:

```
  ✈  AirplaneMode is ready

  Open    http://airplane.mode:8080       (or http://<LAN_IP>:8080)
  Admin   http://airplane.mode:8080/admin/
  Admin password: <pw>   (write it down; it is also in /opt/airplanemode/.env)

  Next: open the admin panel, rename your hotspot and give it a password.
  Update later: run this installer again, or sh /opt/airplanemode/scripts/update.sh
```

The password line only appears if `ADMIN_PASSWORD` is set. `airplane.mode` resolves because
router-setup.sh added the dnsmasq address entry.

## Re-run behaviour, summarised

| Thing | First run | Re-run |
|---|---|---|
| checkout | clone (or tarball) | `git pull --ff-only` (tarball install: stops, see above) |
| `.env` | copied from profile | kept |
| `LAN_IP` | from uci / `--lan-ip` | re-detected and overwritten |
| router login password | created | rotated by router-setup.sh |
| `ADMIN_PASSWORD` | generated by update.sh | kept |
| `ROUTER_URL` | profile default, maybe switched to LAN by the probe | kept, re-probed |

## Changing the installer: checklist

- New option: add to `main()`'s `case`, to `usage()`, to the page's config tool (`render()`
  in `index.html`), and to README's option list. Keep names identical.
- New device: `detect_device` pattern, the `case` at `install.sh:117`, the docker-missing
  hint at `install.sh:119-124`, free-space `need`, a matching `hardware/<name>.env` in the
  platform, and a tab + guide + `DEVICES` entry in `index.html`.
- Router changes: put them in `../airplanemode/scripts/router-setup.sh` (and its ACL rules),
  not here.
- Run shellcheck with the CI flags and the OpenWrt container test (testing.md).
