{
  linuxKernel,
  llvmPackages_21,
  fetchFromGitHub,
  kernelPatches ? [ ],
  randstructSeed ? "",
  features ? { },
}:
let
  src = fetchFromGitHub {
    owner = "GravityLinux";
    repo = "linux";
    rev = "4fc326f6c25ccceb7515e2635c22e01fde5d3bac";
    hash = "sha256-BFxkVA+kIQOUyJnK1jIMW/kJCmaRmTjZhq6q0AM5Rug=";
  };
  configfile = builtins.toFile "gravity-j773g-nixos.config" (
    builtins.readFile ./j773g.config
    + builtins.readFile ./j773g.fragment
    + builtins.readFile ./nixos.fragment
  );
in
(linuxKernel.manualConfig {
  version = "7.1.13";
  modDirVersion = "7.1.13-nixos-gravity";
  inherit src;
  inherit kernelPatches randstructSeed;
  features = features // { efiBootStub = true; };
  inherit configfile;
  allowImportFromDerivation = true;
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
