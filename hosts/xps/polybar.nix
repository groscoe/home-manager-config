{ config, lib, pkgs, ... }:
let
  fonts = import ./polybar-fonts.nix { inherit pkgs lib; };
  start = pkgs.writeShellScriptBin "xps-start-polybar" ''
    set -eu
    [ -n "''${DISPLAY:-}" ] || exit 0
    ${config.systemd.user.systemctlPath} --user import-environment DISPLAY XAUTHORITY
    exec ${config.systemd.user.systemctlPath} --user start polybar.service
  '';
in {
  home.packages = [ start fonts.text fonts.icons ];
  services.polybar = {
    enable = true;
    package = pkgs.polybarFull;
    script = ''
      exec ${config.services.polybar.package}/bin/polybar --log=warning \
        --config=${config.home.homeDirectory}/.config/polybar/material/config.ini main
    '';
  };
  # One foreground process gives systemd an unambiguous main PID. The original
  # theme and its scripts remain under the existing managed .config/polybar.
  systemd.user.services.polybar.Service = {
    Type = lib.mkForce "simple";
    # Preserve access to declared menu tools and Ubuntu's lock/power integration.
    Environment = lib.mkForce [
      "PATH=${config.home.profileDirectory}/bin:/usr/local/bin:/usr/bin:/bin"
      "DESKTOP_SESSION=i3"
    ];
  };
}
