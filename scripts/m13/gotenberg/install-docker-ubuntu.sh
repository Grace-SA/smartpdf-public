#!/bin/sh
# Run only in the dedicated Ubuntu PoC distribution, as root.
# Based on https://docs.docker.com/engine/install/ubuntu/
set -eu
. /etc/os-release
test "$ID" = ubuntu
test "$(id -u)" = 0
if command -v docker >/dev/null 2>&1; then
  docker version
  exit 0
fi
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
printf '%s\n' \
  'Types: deb' \
  'URIs: https://download.docker.com/linux/ubuntu' \
  "Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}" \
  'Components: stable' \
  "Architectures: $(dpkg --print-architecture)" \
  'Signed-By: /etc/apt/keyrings/docker.asc' \
  > /etc/apt/sources.list.d/docker.sources
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
if command -v systemctl >/dev/null 2>&1 && test -d /run/systemd/system; then
  systemctl start docker
else
  service docker start
fi
docker version
