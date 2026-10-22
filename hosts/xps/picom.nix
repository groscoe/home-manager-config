{ config, lib, pkgs, ... }:
let
  start = pkgs.writeShellScriptBin "xps-start-picom" ''
    set -eu
    # i3 owns the real X11 session. Import only its display credentials.
    [ -n "''${DISPLAY:-}" ] || exit 0
    ${config.systemd.user.systemctlPath} --user import-environment DISPLAY XAUTHORITY
    exec ${config.systemd.user.systemctlPath} --user start picom.service
  '';
  preserveSharing = pkgs.writeShellScript "picom-preserve-xps-desktop" ''
    set -eu
    # A compositor restart during sharing must reapply the VNC bypass.
    if ! ${config.systemd.user.systemctlPath} --user is-active --quiet xps-desktop.service; then
      exit 0
    fi
    bus_name="com.github.chjj.compton.''${DISPLAY//[^A-Za-z0-9]/_}"
    for attempt in {1..50}; do
      if ${pkgs.dbus}/bin/dbus-send --session --print-reply \
        --dest=org.freedesktop.DBus /org/freedesktop/DBus \
        org.freedesktop.DBus.GetNameOwner "string:$bus_name" >/dev/null 2>&1; then
        exec ${config.home.profileDirectory}/bin/xps-desktop-control refresh-display
      fi
      ${pkgs.coreutils}/bin/sleep 0.1
    done
    echo "Picom's control interface did not become ready during desktop sharing" >&2
    exit 1
  '';
in {
  home.packages = [ start ];
  services.picom = {
    enable = true;
    package = config.lib.nixGL.wrap pkgs.picom;
    # Keep the existing appearance and VNC/lock-screen options without the
    # module's defaults overriding this host's established configuration.
    settings = lib.mkForce {};
    extraConfig = builtins.readFile ../../picom/config/picom/picom.conf;
  };
  systemd.user.services.picom.Service = {
    ExecStartPost = preserveSharing;
    Restart = lib.mkForce "on-failure";
  };
}
