#!/bin/sh
# NixOS on Mac mini (M4): release bootstrap.
# This script is intended to be served at the project's stable install URL.
set -eu
PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH

DISTRO='NixOS Gravity'
INSTALLER_BASE=${NIXOS_GRAVITY_INSTALLER_BASE:-https://github.com/a-rustacean/nixos-gravity/releases/latest/download}
INSTALLER_BASE=${INSTALLER_BASE%/}

fail() {
    printf '%s\n' "$DISTRO installer: $*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
NixOS Gravity installer for supported Mac mini (M4) models.

Usage:
  curl -fsSL https://raw.githubusercontent.com/a-rustacean/nixos-gravity/main/install.sh | sh
  sh install.sh --preflight

The installer must be run from macOS as a regular user. The installation kit
will ask for administrator authorization only when needed.

Options:
  --preflight  Check this Mac and the published model list without changing anything
  --help       Show this message
EOF
}

check_host() {
    [ "$(uname -s)" = Darwin ] || fail 'run this from macOS, not Linux.'
    [ "$(uname -m)" = arm64 ] || fail 'only Apple Silicon is supported.'
    [ -d /System ] || fail 'macOS system volume was not found.'

    MODEL=$(/usr/sbin/sysctl -n hw.model 2>/dev/null || true)
    [ -n "$MODEL" ] || fail 'could not determine this Mac model.'
    MACHINE_NAME=$(/usr/sbin/system_profiler -json SPHardwareDataType 2>/dev/null |
        /usr/bin/plutil -extract SPHardwareDataType.0.machine_name raw -o - - 2>/dev/null || true)
    [ "$MACHINE_NAME" = 'Mac mini' ] ||
        fail "unsupported Mac family '${MACHINE_NAME:-unknown}'; this installer supports Mac mini (M4) models only."

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
}

print_host() {
    printf '%s\n' 'Preflight passed:'
    printf '  Model:      %s (%s)\n' "$MODEL" "$MACHINE_NAME"
    printf '  macOS:      %s\n' "$(/usr/bin/sw_vers -productVersion)"
    printf '  Processor:  %s\n' "$(uname -m)"
    printf '  Disk state: unchanged by preflight\n'
}

case "${1:-}" in
    --help | -h)
        usage
        exit 0
        ;;
    --preflight)
        [ "$#" -eq 1 ] || fail '--preflight does not accept additional arguments.'
        preflight=1
        ;;
    *) preflight=0 ;;
esac

check_host

case "$INSTALLER_BASE" in
    https://*) ;;
    *) fail 'installer base URL must use HTTPS.' ;;
esac

version=$(/usr/bin/curl --fail --silent --show-error --location --retry 3 "$INSTALLER_BASE/latest") ||
    fail "could not read the release version from $INSTALLER_BASE/latest."
case "$version" in
    '' | *[!A-Za-z0-9._+-]*) fail 'release version contains invalid characters.' ;;
esac

work=$(/usr/bin/mktemp -d /private/tmp/nixos-gravity-install.XXXXXXXX) || fail 'could not create a temporary directory.'
trap 'rm -rf "$work"' 0

models_file="$work/supported-models.txt"
/usr/bin/curl --fail --silent --show-error --location --retry 3 \
    -o "$models_file" "$INSTALLER_BASE/supported-models.txt" ||
    fail 'could not download the supported-model list.'
[ -s "$models_file" ] || fail 'the release supported-model list is empty.'

kit_id=$(awk -v model="$MODEL" '$1 == model { print $2; exit }' "$models_file")
if [ -z "$kit_id" ]; then
    supported=$(awk '{ print $1 }' "$models_file" | tr '\n' ' ')
    fail "this release does not support $MODEL. Supported models: $supported"
fi
case "$kit_id" in
    '' | *[!a-z0-9-]*) fail 'release model list contains an invalid kit name.' ;;
esac

if [ "$preflight" -eq 1 ]; then
    print_host
    printf '  Release:    %s (%s)\n' "$version" "$kit_id"
    exit 0
fi

archive="installer-$version-$kit_id.tar.gz"

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
[ -f "$work/SUPPORTED-MODELS" ] || fail 'release kit does not contain a model list.'
grep -Fx "$MODEL" "$work/SUPPORTED-MODELS" >/dev/null ||
    fail "the downloaded kit does not support $MODEL."
(cd "$work" && /usr/bin/shasum -a 256 -c SHA256SUMS) || fail 'release kit file verification failed.'

printf '\n%s\n' 'Starting the verified installer kit.'
/usr/bin/caffeinate -dis /bin/bash "$work/Install.command" "$@"
