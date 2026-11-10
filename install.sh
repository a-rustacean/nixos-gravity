#!/bin/sh
# NixOS on the base M4 Mac mini: release bootstrap.
# This script is intended to be served at the project's stable install URL.
set -eu
PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH

DISTRO='NixOS Gravity'
INSTALLER_BASE=${NIXOS_GRAVITY_INSTALLER_BASE:-https://install.nixos-gravity.org/installer}
INSTALLER_BASE=${INSTALLER_BASE%/}

fail() {
    printf '%s\n' "$DISTRO installer: $*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
NixOS Gravity installer for the base M4 Mac mini (Mac16,10 / J773g).

Usage:
  curl -fsSL https://install.nixos-gravity.org | sh
  sh install.sh --preflight

The installer must be run from macOS as a regular user. The installation kit
will ask for administrator authorization only when needed.

Options:
  --preflight  Check this Mac without downloading or changing anything
  --help       Show this message
EOF
}

check_host() {
    [ "$(uname -s)" = Darwin ] || fail 'run this from macOS, not Linux.'
    [ "$(uname -m)" = arm64 ] || fail 'only Apple Silicon is supported.'
    [ -d /System ] || fail 'macOS system volume was not found.'

    model=$(/usr/sbin/sysctl -n hw.model 2>/dev/null || true)
    [ "$model" = Mac16,10 ] || fail "unsupported model '$model'; only Mac16,10 (base M4 Mac mini / J773g) is supported."

    [ "$(/usr/bin/id -u)" -ne 0 ] || fail 'run as your normal macOS user, without sudo.'

    version=$(/usr/bin/sw_vers -productVersion)
    case "$version" in
        '' | *[!0-9.]* | .* | *..* | *.) fail "could not parse macOS version '$version'." ;;
    esac
    old_ifs=$IFS
    IFS=.
    set -- $version
    IFS=$old_ifs
    major=${1:-0}
    minor=${2:-0}
    patch=${3:-0}
    case "$major:$minor:$patch" in
        *[!0-9:]* | :* | *::*) fail "could not parse macOS version '$version'." ;;
    esac
    if [ "$major" -lt 26 ] || { [ "$major" -eq 26 ] && { [ "$minor" -lt 6 ] || { [ "$minor" -eq 6 ] && [ "$patch" -lt 2 ]; }; }; }; then
        fail "macOS $version is too old; version 26.6.2 or newer is required."
    fi

    /usr/bin/curl --version >/dev/null 2>&1 || fail 'curl is unavailable.'
    /usr/bin/shasum -a 256 /dev/null >/dev/null 2>&1 || fail 'shasum is unavailable.'

    printf '%s\n' 'Preflight passed:'
    printf '  Model:      %s (base M4 Mac mini / J773g)\n' "$model"
    printf '  macOS:      %s\n' "$version"
    printf '  Processor:  %s\n' "$(uname -m)"
    printf '%s\n' '  Disk state: unchanged by preflight'
}

case "${1:-}" in
    --help | -h)
        usage
        exit 0
        ;;
    --preflight)
        [ "$#" -eq 1 ] || fail '--preflight does not accept additional arguments.'
        check_host
        exit 0
        ;;
esac

check_host

case "$INSTALLER_BASE" in
    https://*) ;;
    *) fail 'installer base URL must use HTTPS.' ;;
esac

printf '\n%s\n' 'Preparing the NixOS Gravity installer kit...'
version=$(/usr/bin/curl --fail --silent --show-error --location --retry 3 "$INSTALLER_BASE/latest") ||
    fail "could not read the release version from $INSTALLER_BASE/latest."
case "$version" in
    '' | *[!A-Za-z0-9._+-]*) fail 'release version contains invalid characters.' ;;
esac

archive="installer-$version.tar.gz"
work=$(/usr/bin/mktemp -d /private/tmp/nixos-gravity-install.XXXXXXXX) || fail 'could not create a temporary directory.'
trap 'rm -rf "$work"' 0

if ! /usr/bin/curl --fail --silent --show-error --location --retry 3 \
    -o "$work/$archive" "$INSTALLER_BASE/$archive"; then
    fail "could not download $archive."
fi
if ! /usr/bin/curl --fail --silent --show-error --location --retry 3 \
    -o "$work/$archive.sha256" "$INSTALLER_BASE/$archive.sha256"; then
    fail "could not download the checksum for $archive."
fi

expected_name=$(awk 'NR == 1 { print $2 }' "$work/$archive.sha256")
expected_name=${expected_name#\*}
[ "$expected_name" = "$archive" ] || fail 'checksum file names an unexpected archive.'
(cd "$work" && /usr/bin/shasum -a 256 -c "$archive.sha256") || fail 'installer archive checksum failed.'

# Reject absolute paths and parent-directory traversal before unpacking.
if /usr/bin/tar -tzf "$work/$archive" | awk '
    /^\// || /(^|\/)\.\.(\/|$)/ { bad = 1 }
    END { exit bad }
'; then
    :
else
    fail 'installer archive contains an unsafe path.'
fi

/usr/bin/tar -xzf "$work/$archive" -C "$work"
[ -f "$work/Install.command" ] || fail 'release kit does not contain Install.command.'
[ -f "$work/SHA256SUMS" ] || fail 'release kit does not contain SHA256SUMS.'
(cd "$work" && /usr/bin/shasum -a 256 -c SHA256SUMS) || fail 'release kit file verification failed.'

printf '\n%s\n' 'Starting the verified installer kit.'
/usr/bin/caffeinate -dis /bin/bash "$work/Install.command" "$@"
