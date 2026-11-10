{
  lib,
  linuxKernel,
  llvmPackages_21,
  fetchFromGitHub,
  runCommand,
  bash,
  kernelPatches ? [ ],
  randstructSeed ? "",
  features ? { },
}:
let
  src = fetchFromGitHub {
    owner = "GravityLinux";
    repo = "linux";
    rev = "4fc326f6c25ccceb7515e2635c22e01fde5d3bac";
    hash = "sha256-DxH3lrWAutnskHuP+6Q7NRHupPYBip68Poq4pjsV/yM=";
  };
  parseConfig = text:
    builtins.foldl' (
      config: line:
      let
        set = builtins.match "(CONFIG_[^=]+)=([ymn])" line;
        unset = builtins.match "# (CONFIG_[^ ]+) is not set" line;
      in
      if set != null then
        config // { "${builtins.elemAt set 0}" = builtins.elemAt set 1; }
      else if unset != null then
        config // { "${builtins.elemAt unset 0}" = "n"; }
      else
        config
    ) { } (lib.splitString "\n" text);
  config =
    parseConfig (builtins.readFile ./j773g.config)
    // parseConfig (builtins.readFile ./j773g.fragment)
    // parseConfig (builtins.readFile ./nixos.fragment);
  configfile = runCommand "gravity-j773g-nixos.config" { nativeBuildInputs = [ bash ]; } ''
    mkdir -p "$TMPDIR/config"
    ${bash}/bin/bash ${src}/scripts/kconfig/merge_config.sh \
      -m -O "$TMPDIR/config" \
      ${./j773g.config} ${./j773g.fragment} ${./nixos.fragment}
    cp "$TMPDIR/config/.config" "$out"
  '';
in
(linuxKernel.manualConfig {
  version = "7.1.13";
  modDirVersion = "7.1.13-nixos-gravity";
  inherit src;
  inherit kernelPatches randstructSeed;
  inherit config;
  features = features // { efiBootStub = true; };
  inherit configfile;
  stdenv = llvmPackages_21.stdenv;
  extraMakeFlags = [
    "LLVM=1"
    "HOSTLDFLAGS=-fuse-ld=bfd"
  ];
  extraMeta.platforms = [ "aarch64-linux" ];
}).overrideAttrs
  (old: {
    # Keep build metadata deterministic and identifiable as the NixOS package.
    env = (old.env or { }) // {
      KBUILD_BUILD_USER = "nixos-gravity";
      KBUILD_BUILD_HOST = "j773g";
    };
  })
