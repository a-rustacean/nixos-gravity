# J773g kernel configuration provenance

`j773g.config` is the generated AArch64 config used by Omarchy-M4-Native's
J773g Gravity kernel package (GravityLinux/linux commit
`4fc326f6c25ccceb7515e2635c22e01fde5d3bac`). It is based on the
asahi-alarm 7.1.13 config, with Omarchy's board-specific choices in
`j773g.fragment`. The kernel source and hardware patches built here are the
pinned Gravity Linux tree, not the Asahi Linux NixOS support packages.

The NixOS fragment selects a separate module version and the built-in storage,
EFI-stub, root-filesystem, and gzip-initrd options required by this initial
configuration. Re-check the merged `.config` after any kernel or nixpkgs update.

This is a build/evaluation starting point, not yet a hardware-qualified kernel
or installable image. Root credentials and the ESP layout must be set up safely
by the interactive installer before publishing an installer kit.
