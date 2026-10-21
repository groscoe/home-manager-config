{ pkgs, ... }:
let
  preview = pkgs.writeShellApplication {
    name = "file-preview";
    runtimeInputs = [
      pkgs.coreutils pkgs.file pkgs.lsd pkgs.imagemagick
      pkgs.viu pkgs.poppler-utils pkgs.bat
    ];
    text = builtins.readFile ./file-preview.sh;
  };
  dice = pkgs.writeShellScriptBin "dice" ''
    exec ${pkgs.python3}/bin/python3 ${./dice.py} "$@"
  '';
in {
  home.packages = [ preview dice ];
}
