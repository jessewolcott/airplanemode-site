#!/bin/sh
# AirplaneMode installer. Run it on the router, as root, while the router is online:
#
#   curl -fsSL https://raw.githubusercontent.com/jessewolcott/airplanemode-site/main/install.sh | sh
#
# Options go after "sh -s --" (see usage() below for the list), for example:
#   curl -fsSL https://raw.githubusercontent.com/jessewolcott/airplanemode-site/main/install.sh | sh -s -- --device glinet
#
# Why curl: OpenWrt's built-in wget (uclient-fetch + libustream-mbedtls, 24.10) fails the TLS
# handshake with GitHub's servers, while curl on the same mbedTLS works. If curl is missing,
# install it first (the setup page's command does): opkg update && opkg install curl
#
# Safe to run again: an existing install is updated, and its .env (passwords) is kept.
# Everything below runs from main() at the very end, so a half-downloaded script does nothing.

REPO=https://github.com/jessewolcott/airplanemode.git
TARBALL=https://codeload.github.com/jessewolcott/airplanemode/tar.gz/refs/heads

say()  { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mStopped:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
	cat <<'EOF'
AirplaneMode installer. Run on the router as root, while it's online:
  curl -fsSL https://raw.githubusercontent.com/jessewolcott/airplanemode-site/main/install.sh | sh -s -- [options]

  --device NAME     nanopi-r6s or glinet (default: detected)
  --lan-ip ADDR     the router's LAN address (default: read from the router)
  --wan NAME        name of the wired WAN interface (default: wan)
  --keep-rebind     keep DNS rebind protection on
  --no-wireguard    don't install WireGuard (no home VPN)
  --dir PATH        where to install (default: /opt/airplanemode)
  --branch NAME     platform branch to install (default: main)
EOF
}

pkg_install() {
	if command -v apk >/dev/null 2>&1; then
		apk update >/dev/null 2>&1 && apk add "$@" >/dev/null 2>&1
	elif command -v opkg >/dev/null 2>&1; then
		opkg update >/dev/null 2>&1 && opkg install "$@" >/dev/null 2>&1
	else
		return 1
	fi
}

# Download a URL to stdout. curl if possible (see the note at the top), else wget.
fetch() {
	if command -v curl >/dev/null 2>&1; then
		curl -fsSL -m 600 --retry 2 "$1"
	else
		wget -q -T 30 -O - "$1"
	fi
}

ensure_curl() {
	command -v curl >/dev/null 2>&1 && return 0
	if pkg_install curl ca-bundle; then ok "installed curl"; else warn "couldn't install curl; trying the built-in wget"; fi
}

# KEY=VALUE in .env: replace the line if it's there, otherwise append it.
set_env() {
	if grep -qE "^$1=" "$DIR/.env"; then
		sed -i "s|^$1=.*|$1=$2|" "$DIR/.env"
	else
		printf '%s=%s\n' "$1" "$2" >>"$DIR/.env"
	fi
}
get_env() { grep -E "^$1=" "$DIR/.env" 2>/dev/null | tail -n 1 | cut -d= -f2-; }

detect_device() {
	info="$(cat /tmp/sysinfo/board_name /tmp/sysinfo/model 2>/dev/null; { tr -d '\000' </proc/device-tree/model; } 2>/dev/null)"
	case "$(printf '%s' "$info" | tr '[:upper:]' '[:lower:]')" in
		*nanopi-r6s* | *"nanopi r6s"*) echo nanopi-r6s ;;
		*glinet* | *gl-* | *gl.inet*) echo glinet ;;
		*) if [ -f /etc/glversion ]; then echo glinet; fi ;;
	esac
	return 0
}

detect_lan_ip() {
	# ipaddr can be "192.168.2.1", "192.168.2.1/24" or a list of them
	set -- $(uci -q get network.lan.ipaddr || true)
	if [ $# -gt 0 ]; then echo "${1%%/*}"; fi
	return 0
}

valid_ip() {
	case "$1" in
		*[!0-9.]* | *..* | .* | *.) return 1 ;;
	esac
	[ "$(echo "$1" | tr -cd . | wc -c)" -eq 3 ] || return 1
	for part in $(echo "$1" | tr . ' '); do
		[ "${#part}" -le 3 ] && [ "$part" -le 255 ] || return 1
	done
}

preflight() {
	say "Checking the router"
	[ "$(id -u)" = 0 ] || die "run this as root (ssh root@<router>)."
	command -v uci >/dev/null 2>&1 || die "this doesn't look like OpenWrt (no uci command)."
	ok "OpenWrt, running as root"

	arch=$(uname -m)
	[ "$arch" = aarch64 ] || die "AirplaneMode's images are arm64 only; this router is $arch."
	ok "arm64 CPU"

	if [ -z "$DEVICE" ]; then
		DEVICE=$(detect_device)
		[ -n "$DEVICE" ] || die "couldn't tell which device this is. Add --device nanopi-r6s or --device glinet."
		ok "device: $DEVICE (detected)"
	else
		ok "device: $DEVICE"
	fi
	case "$DEVICE" in nanopi-r6s | glinet) ;; *) die "unknown device '$DEVICE' (use nanopi-r6s or glinet)." ;; esac

	command -v docker >/dev/null 2>&1 || {
		if [ "$DEVICE" = nanopi-r6s ]; then
			die "Docker isn't installed. Flash the FriendlyWrt image with 'docker' in its name (see the setup page)."
		else
			die "Docker isn't installed. Install dockerd, docker and docker-compose on USB/SD storage first (see the setup page)."
		fi
	}
	docker info >/dev/null 2>&1 || die "Docker is installed but not running. Try: /etc/init.d/dockerd start"
	docker compose version >/dev/null 2>&1 || die "Docker is missing the 'compose' plugin. Install docker-compose (v2)."
	ok "Docker $(docker version -f '{{.Server.Version}}' 2>/dev/null) with compose"

	ensure_curl
	fetch https://github.com >/dev/null 2>&1 \
		|| die "the router can't reach github.com. Get it online first (Ethernet into WAN, or join a Wi-Fi in LuCI)."
	ok "online"

	need=3000000; [ "$DEVICE" = glinet ] && need=1200000   # KB: images (+ model + Wikivoyage on the R6S)
	root=$(docker info -f '{{.DockerRootDir}}' 2>/dev/null); [ -d "$root" ] || root=/
	free=$(df -k "$root" 2>/dev/null | awk 'NR==2 {print $4}')
	case "$free" in
		'' | *[!0-9]*) warn "couldn't check free space; about $((need / 1024)) MB is needed." ;;
		*) if [ "$free" -lt "$need" ]; then
			warn "only $((free / 1024)) MB free for Docker at $root; about $((need / 1024)) MB is needed."
		else
			ok "$((free / 1024)) MB free for Docker"
		fi ;;
	esac

	radios=$(uci -q show wireless | grep -c '=wifi-device$' || true)
	if [ "$radios" -ge 2 ]; then
		ok "$radios Wi-Fi radios"
	elif [ "$radios" -eq 1 ]; then
		warn "only 1 Wi-Fi radio found. It works, but two adapters (upstream + hotspot) are faster."
	else
		warn "no Wi-Fi radios yet. Plug in the USB Wi-Fi adapters; the admin panel picks them up later."
	fi
}

fetch_code() {
	say "Getting AirplaneMode ($BRANCH) into $DIR"
	if [ -d "$DIR/.git" ]; then
		if git -C "$DIR" pull --ff-only -q; then ok "updated"; else warn "couldn't update; using the copy already there"; fi
		return
	fi
	if [ -f "$DIR/.snapshot" ]; then
		# An earlier install without git: unpack a fresh snapshot over it (.env and data volumes stay).
		fetch "$TARBALL/$BRANCH" | tar -xz -C "$DIR" --strip-components=1 || die "download failed."
		date >"$DIR/.snapshot"
		ok "updated the snapshot"
		return
	fi
	[ -e "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ] && die "$DIR exists and isn't an AirplaneMode checkout. Move it or use --dir."
	if ! command -v git >/dev/null 2>&1; then
		if pkg_install git git-http; then ok "installed git"; else warn "couldn't install git; downloading a snapshot instead"; fi
	fi
	mkdir -p "$(dirname "$DIR")"
	if command -v git >/dev/null 2>&1 && git clone -q -b "$BRANCH" "$REPO" "$DIR"; then
		ok "cloned"
	else
		# No git: unpack a snapshot. update.sh then can't pull, so re-run this installer to update.
		mkdir -p "$DIR"
		fetch "$TARBALL/$BRANCH" | tar -xz -C "$DIR" --strip-components=1 || die "download failed."
		date >"$DIR/.snapshot"     # marks a no-git install, so a re-run knows it may update it
		ok "downloaded a snapshot (re-run this installer to update later)"
	fi
}

configure() {
	say "Configuring"
	if [ -f "$DIR/.env" ]; then
		ok "keeping the existing .env (your passwords stay the same)"
	else
		cp "$DIR/hardware/$DEVICE.env" "$DIR/.env"
		chmod 600 "$DIR/.env"
		ok "profile: hardware/$DEVICE.env"
	fi

	[ -n "$LAN_IP" ] || LAN_IP=$(detect_lan_ip)
	if [ -n "$LAN_IP" ]; then
		valid_ip "$LAN_IP" || die "'$LAN_IP' isn't an IPv4 address."
		set_env LAN_IP "$LAN_IP"
		ok "LAN address: $LAN_IP"
	else
		warn "couldn't read the LAN address; keeping $(get_env LAN_IP) from the profile"
	fi
	if [ -n "$WAN" ]; then
		uci -q get "network.$WAN" >/dev/null || die "there's no network interface called '$WAN'."
		set_env WAN_IFACE "$WAN"
		ok "wired WAN: $WAN"
	fi
}

setup_router() {
	say "Preparing the router (limited login, DNS, Ethernet first, WireGuard)"
	( cd "$DIR" && KEEP_REBIND_PROTECTION=$KEEP_REBIND SKIP_WIREGUARD=$NO_WG sh scripts/router-setup.sh ) \
		|| die "router setup failed (see above)."
}

start_stack() {
	say "Downloading and starting the apps (about 1.8 GB the first time, so this takes a while)"
	( cd "$DIR" && sh scripts/update.sh ) || die "starting the apps failed (see above). Fix it and run this again."
}

# Can the admin service log in to the router's API? If not via host.docker.internal,
# try the LAN address, which some firewalls allow when the Docker gateway isn't.
check_router_api() {
	say "Checking that the admin panel can control the router"
	probe='import json,os,sys,urllib.request
u=sys.argv[1]
b=json.dumps({"jsonrpc":"2.0","id":1,"method":"call","params":["00000000000000000000000000000000","session","login",{"username":os.environ["ROUTER_USER"],"password":os.environ["ROUTER_PASSWORD"]}]}).encode()
try:
    r=json.load(urllib.request.urlopen(urllib.request.Request(u,b,{"Content-Type":"application/json"}),timeout=8))
    sys.exit(0 if r.get("result",[1])[0]==0 else 2)
except Exception:
    sys.exit(1)'
	cd "$DIR"
	url=$(get_env ROUTER_URL); url=${url:-http://host.docker.internal/ubus}
	if docker compose exec -T admin python -c "$probe" "$url" 2>/dev/null; then
		ok "router API reachable at $url"
		return
	fi
	alt="http://$(get_env LAN_IP)/ubus"
	if [ "$alt" != "$url" ] && docker compose exec -T admin python -c "$probe" "$alt" 2>/dev/null; then
		set_env ROUTER_URL "$alt"
		docker compose up -d admin >/dev/null 2>&1
		ok "router API reachable at $alt (saved to .env)"
		return
	fi
	warn "the admin panel can't reach the router's API yet. In LuCI → Network → Firewall, allow"
	warn "input from the 'docker' zone, then run this installer again. Status pages still work."
}

finish() {
	ip=$(get_env LAN_IP); port=$(get_env HTTP_PORT); port=${port:-8080}
	pw=$(get_env ADMIN_PASSWORD)
	printf '\n\033[1;33m  ✈  AirplaneMode is ready\033[0m\n\n'
	printf '  Open    http://airplane.mode:%s       (or http://%s:%s)\n' "$port" "$ip" "$port"
	printf '  Admin   http://airplane.mode:%s/admin/\n' "$port"
	[ -n "$pw" ] && printf '  Admin password: \033[1m%s\033[0m   (write it down; it is also in %s/.env)\n' "$pw" "$DIR"
	printf '\n  Next: open the admin panel, rename your hotspot and give it a password.\n'
	printf '  Update later: run this installer again, or sh %s/scripts/update.sh\n\n' "$DIR"
}

main() {
	DEVICE=""; LAN_IP=""; WAN=""; KEEP_REBIND=0; NO_WG=0
	DIR=/opt/airplanemode; BRANCH=main
	while [ $# -gt 0 ]; do
		case "$1" in
			--device) DEVICE=${2:-}; shift ;;
			--lan-ip) LAN_IP=${2:-}; shift ;;
			--wan) WAN=${2:-}; shift ;;
			--keep-rebind) KEEP_REBIND=1 ;;
			--no-wireguard) NO_WG=1 ;;
			--dir) DIR=${2:-}; shift ;;
			--branch) BRANCH=${2:-}; shift ;;
			-h | --help) usage; exit 0 ;;
			*) die "unknown option: $1 (see --help)" ;;
		esac
		shift
	done
	[ -n "$DIR" ] && [ -n "$BRANCH" ] || die "--dir and --branch need a value."

	printf '\n\033[1;33m  ✈  AirplaneMode installer\033[0m\n\n'
	preflight
	fetch_code
	configure
	setup_router
	start_stack
	check_router_api
	finish
}

set -eu
main "$@"
