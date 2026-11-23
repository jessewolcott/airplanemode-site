# Gotchas and invariants

## Installer

- **OpenWrt wget can't talk to GitHub.** uclient-fetch + libustream-mbedtls (24.10) fails
  the TLS handshake with `github.com`, `codeload.github.com`, `*.github.io`; curl on the same
  mbedTLS works. Every download must go through `fetch` (curl first). The page's command
  installs curl before downloading the script.
- **Keep `main "$@"` the last line**, with `set -eu` right before it. Top-level commands
  anywhere else would run from a half-downloaded script.
- **POSIX sh / busybox ash only.** No `local`, `[[ ]]`, arrays, `$'...'`, `echo -e`,
  `${var,,}` (lower-casing is done with `tr`). shellcheck `-s sh` in CI catches most.
- **`set -e` and `$(...)`**: helper functions used in command substitution end with
  `return 0` (`detect_device`, `detect_lan_ip`) or `|| true`, so a "not found" doesn't abort
  the run. Keep that pattern for new detectors. `grep -c` returns 1 when the count is 0, hence
  `|| true` in the radio count.
- **Line endings.** `.gitattributes` forces LF for `*.sh` and `tests/docker-stub`. A CRLF
  `install.sh` breaks under ash (`\r` in commands). git's `autocrlf` is on on the dev
  machine, so don't remove those rules; add any new script type to them.
- **`set_env` uses `sed "s|...|...|"`**: a value with `|`, `&` or `\` would corrupt `.env`.
  Fine for IPs, interface names and URLs; escape if that ever changes.
- **`valid_ip` doesn't range-check octets.** The page's validator does; direct CLI users
  can pass `300.1.1.1`.
- **`--device` with no value as the last argument** hits a bare `shift` with nothing left;
  the shell aborts with its own error, not the friendly one.
- **`.env` is never replaced on re-run.** Switching `--device` on an existing install keeps
  the old profile's settings; delete `.env` (losing passwords) to switch. `LAN_IP` is
  re-detected and rewritten every run, and router-setup.sh rotates the router password every
  run.
- **`--branch` only applies to a fresh install.** Updates do `git pull --ff-only` on
  whatever branch is checked out.
- **Tarball installs can't be re-run as-is.** No `.git` + non-empty dir -> "isn't an
  AirplaneMode checkout". The message after a snapshot install says to re-run to update,
  but a re-run only gets past that check if the folder is moved away first (and `.env`
  copied back to keep the passwords). Untested path.
- **Router-API probe failure is a warning, not an error.** The install "succeeds" even when
  the admin panel can't control the router; the fix is allowing input from the `docker`
  firewall zone in LuCI, or `ROUTER_URL=http://<LAN_IP>/ubus` (which the installer tries).
- **Free space and radios only warn.** Low disk shows up later as `update.sh` pull failures.
- **Detection strings are unverified.** `nanopi-r6s`, `gl-`, `glinet`, `gl.inet`,
  `/etc/glversion` come from OpenWrt/GL.iNet conventions, not from a real board.
- **apk vs opkg**: `pkg_install` prefers apk. Only opkg (24.10) is tested.
- **Don't add router changes here.** They go into `../airplanemode/scripts/router-setup.sh`
  and, if they need new ubus calls or uci configs, the rpcd ACL file and the platform's
  live-test denied list (platform CLAUDE.md).

## Page

- **Option names live in two places**: `install.sh` `main()` and `index.html` `render()`.
  Rename or add in both, plus README and `usage()`.
- **New device = four places**: `detect_device`, the `case` at `install.sh:117` (and the
  docker hint / free-space need), a `.device` tab + `.guide` with `data-device` and
  `data-step` ids in `index.html`, and a `DEVICES` entry (label + default IP). The guide's
  install step needs a `.tool-slot`.
- **The tool is one DOM node that moves between guides.** Don't clone it per guide; ids
  (`#t-lan` etc.) would duplicate and saved state would split.
- **The rebind checkbox is inverted**: checked = rebind protection off = no flag; unchecked
  = `--keep-rebind`.
- **Invalid input is silently dropped from the command**, only marked red. Intentional (the
  command must never contain unvalidated text), but it means a typo'd IP gives a command
  without `--lan-ip`.
- **`installUrl` uses the serving origin only over https.** A local http preview always
  shows the raw GitHub URL; that is expected, not a bug.
- **Clipboard API needs a secure context.** On plain http (non-localhost) copy falls back to
  `execCommand("copy")`.
- **localStorage keys** `am.device`, `am.opts`, `am.done` persist per browser; renaming
  step ids or option keys leaves stale entries (harmless).
- **Static values duplicated**: default IPs (`192.168.2.1`, `192.168.8.1`) in `DEVICES`, in
  guide text, and in the platform profiles; port 8080 in the admin links. Keep consistent if
  the platform changes them.
- **Assets are copies** of platform files (`portal/icon.svg`, `docs/screenshots/*`).
  Refresh them when the platform UI changes. `drop.png` and `admin-vpn-devices.png` are
  currently unused by the page.
- **Keep the visual style matched** to `../airplanemode/portal/index.html` (dark, amber
  `#f2b34b`).

## Process

- Pushing to `main` changes the live installer for everyone (raw GitHub URL). CI runs
  after the push, not before; run shellcheck and the container test locally first.
- CI clones the platform's live `main`; a platform change can break this repo's CI.
- Everything is *untested on real hardware*; say so in docs and pages.
