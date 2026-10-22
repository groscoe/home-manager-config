{ config, lib, pkgs, ... }:
let
  entries = pkgs.runCommand "xps-desktop-entries" { } ''
    mkdir -p "$out"
    for entry in ${config.home.path}/share/applications/*.desktop; do
      ln -s "$entry" "$out/$(basename "$entry")"
    done
  '';
in {
  xdg.systemDirs.data = lib.mkBefore [
    "${config.home.profileDirectory}/share"
    "/usr/local/share"
    "/usr/share"
  ];

  # The running i3 session can discover these immediately, even if it inherited
  # Ubuntu's old XDG_DATA_DIRS before Home Manager was installed.
  xdg.dataFile."applications" = {
    source = entries;
    recursive = true;
  };
  xdg.dataFile."dbus-1/services/org.kde.kdeconnect.service".source =
    "${config.home.path}/share/dbus-1/services/org.kde.kdeconnect.service";
  home.activation.updateXpsDesktopDatabase = lib.hm.dag.entryAfter [ "installPackages" ] ''
    run ${pkgs.desktop-file-utils}/bin/update-desktop-database ${lib.escapeShellArg (config.xdg.dataHome + "/applications")}
  '';
}
