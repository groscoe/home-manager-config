{ pkgs }:
let
  # Nix's pkgconf package exposes only pkgconf. Keep the conventional command
  # available inside these shells as well, using the same wrapped implementation.
  pkgConfig = pkgs.pkgconf.override {
    extraBuildCommands = ''
      ln -s pkgconf "$out/bin/pkg-config"
    '';
  };
  tools = with pkgs; [
    gnumake
    cmake
    ninja
    meson
    autoconf
    automake
    libtool
    pkgConfig
    gdb
  ];
  shell =
    stdenv:
    (pkgs.mkShell.override { inherit stdenv; }) {
      packages = tools;
    };
in
{
  c = shell pkgs.stdenv;
  c-clang = shell pkgs.llvmPackages.stdenv;
}
