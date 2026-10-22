{ lib, pkgs-unstable, ... }:
let
  # The existing unstable pin predates the latest maintenance releases. Keep
  # these small, checksum-pinned updates until that same input catches up.
  # https://www.python.org/downloads/release/python-3151/
  # Extend the local package set so Python's build-time interpreter uses the
  # same source version/hash as its runtime interpreter.
  packages =
    if lib.versionAtLeast pkgs-unstable.python315.version "3.15.1" then
      pkgs-unstable
    else
      pkgs-unstable.extend (
        final: prev: {
          python315 =
            (prev.python315.override {
              self = final.python315;
              sourceVersion = {
                major = "3";
                minor = "15";
                patch = "1";
                suffix = "";
              };
              hash = "sha256-ZzrnIy2EyJRymILIJX0wDvLSZSORG/05F+yM5/Um+Zs=";
            }).overrideAttrs
              (old: {
                # Upstream 3.15.1 added a Windows guard around the MIME file list.
                # Rebase Nixpkgs' existing path substitution while preserving it.
                patches = map (
                  patch:
                  if builtins.baseNameOf (toString patch) == "mimetypes.patch" then
                    ./python-3.15-mimetypes.patch
                  else
                    patch
                ) old.patches;
              });
        }
      );
  python = packages.python315;
  pip = import ./python-pip.nix { inherit lib pkgs-unstable python; };
  environment = python.withPackages (_: [ pip ]);
in
{
  # Neovim has its own absolute-path provider. Give this matching Python/pip
  # pair priority only in the user's PATH, without changing Ubuntu's Python.
  # Project virtual environments still take precedence when activated.
  home.packages = [ (lib.hiPrio environment) ];
}
