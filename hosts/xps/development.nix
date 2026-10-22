{ pkgs-unstable, ... }:
{
  # Safe standalone defaults. Compiler/library stacks and Autotools use the
  # complete environments in dev-shells.nix instead of global search paths.
  home.packages = with pkgs-unstable; [
    gnumake
    gdb
  ];
}
