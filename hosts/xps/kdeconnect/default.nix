{ config, lib, pkgs, pkgs-unstable, ... }:
let
  package = pkgs-unstable.kdePackages.kdeconnect-kde;
  daemon = pkgs.writeShellScript "kdeconnect-session-daemon" ''
    # Linger starts the user manager at boot, before an X session exists.
    # Keep network features available then; use the real clipboard after login.
    if [ -n "''${DISPLAY:-}" ] && ${pkgs.xorg.xdpyinfo}/bin/xdpyinfo >/dev/null 2>&1; then
      export QT_QPA_PLATFORM=xcb
    else
      export QT_QPA_PLATFORM=offscreen
    fi
    exec ${package}/bin/kdeconnectd
  '';
  session = pkgs.writeShellApplication {
    name = "xps-kdeconnect-session";
    runtimeInputs = [ pkgs.python3 ];
    text = ''
      exec python3 ${./session.py} ${config.systemd.user.systemctlPath}
    '';
  };
  menu = pkgs.writeShellApplication {
    name = "rofi-kdeconnect";
    runtimeInputs = [ config.programs.rofi.finalPackage package pkgs.python3 pkgs.libnotify pkgs.systemd ];
    text = ''
      export LC_ALL=C.UTF-8
      exec python3 ${./menu.py} "$@"
    '';
  };
  desktop = pkgs.makeDesktopItem {
    name = "rofi-kdeconnect";
    desktopName = "KDE Connect devices";
    comment = "Find devices, share files and clipboard, and manage KDE Connect";
    exec = "${menu}/bin/rofi-kdeconnect";
    icon = "kdeconnect";
    categories = [ "Network" "Utility" ];
    keywords = [ "phone" "tailscale" "share" "clipboard" "rofi" ];
  };
in {
  services.kdeconnect = { enable = true; inherit package; };
  # i3 does not activate graphical-session.target. With user lingering enabled,
  # default.target also starts this at boot before graphical login.
  systemd.user.services.kdeconnect = {
    Unit = {
      After = lib.mkForce [ "dbus.socket" ];
      PartOf = lib.mkForce [ ];
      StartLimitIntervalSec = 0;
    };
    Install.WantedBy = lib.mkForce [ "default.target" ];
    Service = {
      ExecStart = lib.mkForce (toString daemon);
      Type = "dbus";
      BusName = "org.kde.kdeconnect";
      Restart = lib.mkForce "always";
      RestartSec = 3;
    };
  };
  # Avoid independent Ubuntu/autostart daemons competing for the same bus name.
  xdg.configFile."autostart/org.kde.kdeconnect.daemon.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=KDE Connect (managed by Home Manager)
    Hidden=true
  '';
  xdg.dataFile."dbus-1/services/org.kde.kdeconnect.service".text = ''
    [D-BUS Service]
    Name=org.kde.kdeconnect
    Exec=${package}/bin/kdeconnectd
    SystemdService=kdeconnect.service
  '';
  home.packages = [ menu desktop session ];
  xdg.dataFile."applications/rofi-kdeconnect.desktop".source =
    "${desktop}/share/applications/rofi-kdeconnect.desktop";
}
