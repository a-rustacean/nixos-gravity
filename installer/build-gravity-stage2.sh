#!/usr/bin/env bash
set -euo pipefail

workspace=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
installer="$workspace/gravity-installer"
linux="$workspace/linux"
uboot="$workspace/u-boot"
out="$workspace/out"

verify_ref() {
    local repo=$1 expected=$2 actual
    : "${expected:?expected revision must be set}"
    actual=$(git -C "$repo" rev-parse HEAD)
    [[ "$actual" == "$expected" ]] || {
        printf 'Unexpected source revision in %s: expected %s, got %s\n' \
            "$repo" "$expected" "$actual" >&2
        exit 1
    }
}

verify_ref "$installer" "${GRAVITY_INSTALLER_REF:-}"
verify_ref "$installer/bootloader" "${GRAVITY_BOOTLOADER_REF:-}"
verify_ref "$linux" "${GRAVITY_LINUX_REF:-}"
verify_ref "$uboot" "${GRAVITY_UBOOT_REF:-}"

cd "$installer/bootloader"
make -k -j2 ARCH=aarch64-linux-gnu- RELEASE=1
sh ../tools/append-boot-logo.sh build/m1n1.bin ../artwork

cp -f "$linux"/arch/arm64/boot/dts/apple/*.dts \
    "$linux"/arch/arm64/boot/dts/apple/*.dtsi \
    "$linux"/arch/arm64/boot/dts/apple/*.h \
    "$uboot"/dts/upstream/src/arm64/apple/

make -C "$uboot" CROSS_COMPILE=aarch64-linux-gnu- apple_m1_defconfig
# U-Boot's vendor-DTB option builds every Apple device tree. Several unrelated
# upstream SoC trees contain floating-point DTS extensions that this pinned
# U-Boot dtc cannot parse. This kit targets one model, so make its J773g tree
# the sole default instead of building unrelated Apple DTBs.
"$uboot/scripts/config" --file "$uboot/.config" \
    --disable OF_UPSTREAM_BUILD_VENDOR \
    --set-str DEFAULT_DEVICE_TREE apple/t8132-j773g
make -C "$uboot" CROSS_COMPILE=aarch64-linux-gnu- ARCH=arm olddefconfig
grep -Fx 'CONFIG_DEFAULT_DEVICE_TREE="apple/t8132-j773g"' "$uboot/.config"
if grep -Fxq 'CONFIG_OF_UPSTREAM_BUILD_VENDOR=y' "$uboot/.config"; then
    printf '%s\n' 'U-Boot vendor DTB sweep must be disabled for the J773g-only build' >&2
    exit 1
fi
make -C "$uboot" CROSS_COMPILE=aarch64-linux-gnu- ARCH=arm -j2

mkdir -p "$out/esp/m1n1" "$out/esp/licenses/gravity-artwork"
cp "$installer/artwork/LICENSE" "$installer/artwork/README.md" \
    "$installer/artwork/TRADEMARKS.md" "$out/esp/licenses/gravity-artwork/"
gzip -k "$uboot/u-boot-nodtb.bin"
cat \
    "$installer/bootloader/build/m1n1.bin" \
    "$uboot/dts/upstream/src/arm64/apple/t8132-j773g.dtb" \
    "$uboot/u-boot-nodtb.bin.gz" \
    > "$out/esp/m1n1/boot.bin"

test -s "$out/esp/m1n1/boot.bin"
cp "$workspace/installer/boot-sources.json" "$out/BOOT-SOURCES.json"
(
    cd "$out"
    zip -qr gravity-j773g-stage2.zip esp
    unzip -t gravity-j773g-stage2.zip
    shasum -a 256 gravity-j773g-stage2.zip esp/m1n1/boot.bin BOOT-SOURCES.json > SHA256SUMS
)
