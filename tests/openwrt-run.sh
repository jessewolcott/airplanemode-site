#!/bin/sh
# Runs inside an OpenWrt rootfs container (see .github/workflows/check.yml):
#   docker run --rm --platform linux/aarch64_generic -v "$PWD:/src:ro" \
#     -v "$PWD/tests/docker-stub:/usr/bin/docker:ro" openwrt/rootfs:aarch64_generic-24.10.4 sh /src/tests/openwrt-run.sh
# Docker is a stub, so this covers everything up to "docker compose": preflight, download,
# .env, router-setup.sh, update.sh's password step, the summary, and a re-run.
set -eu
fail() { echo "FAIL: $*" >&2; exit 1; }
mkdir -p /var/lock /var/run /opt/docker

# a minimal router config, like a fresh FriendlyWrt
printf 'config interface lan\n\tlist ipaddr 10.9.8.1/24\n\nconfig interface wan\n\toption proto dhcp\n' >/etc/config/network
printf 'config dnsmasq\n' >/etc/config/dhcp
touch /etc/config/rpcd

out=$(sh /src/install.sh --no-wireguard 2>&1) && fail "should stop: no device detected" || true
echo "$out" | grep -q "couldn't tell which device" || fail "device detection message"

sh /src/install.sh --device nanopi-r6s --no-wireguard
env=/opt/airplanemode/.env
grep -qx 'LAN_IP=10.9.8.1' $env || fail "LAN_IP not read from uci"
grep -qx 'ROUTER_USER=airplanemode' $env || fail "router login not set up"
grep -qE '^ADMIN_PASSWORD=.{16}$' $env || fail "admin password not generated"
[ "$(uci get network.wan.metric)" = 10 ] || fail "wan metric"
uci get dhcp.@dnsmasq[0].address | grep -q '/airplane.mode/10.9.8.1' || fail "airplane.mode name"
pw=$(grep ADMIN_PASSWORD $env)

sh /src/install.sh --device nanopi-r6s --no-wireguard | grep -q "keeping the existing .env" || fail "re-run should keep .env"
[ "$(grep ADMIN_PASSWORD $env)" = "$pw" ] || fail "re-run changed the admin password"
echo "PASS"
