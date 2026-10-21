{ config, pkgs, lib, ... }:
let
  atuinModule = import ../../atuin/atuin.nix { inherit pkgs lib; };
  hiDpiScript = pkgs.writeShellScriptBin "xps-apply-hidpi" ''
    set -eu
    [ -n "''${DISPLAY:-}" ] || exit 0
    ${pkgs.xorg.xrdb}/bin/xrdb -merge ${config.xresources.path}
    ${pkgs.xorg.xsetroot}/bin/xsetroot -xcf \
      ${config.home.pointerCursor.package}/share/icons/breeze_cursors/cursors/left_ptr 48
    ${config.systemd.user.systemctlPath} --user import-environment DISPLAY XAUTHORITY
    ${config.systemd.user.systemctlPath} --user start xsettingsd.service
  '';
in {
  imports = [ ./applications.nix ./ssh.nix ./session.nix ../../clamav-scan ../../rofi/connections.nix ../../secure-boot-tools ];

  assertions = [{
    assertion = pkgs.stdenv.hostPlatform.system == "x86_64-linux";
    message = "The xps profile requires x86_64-linux; create a separate hardware profile for another machine.";
  }];

  home.homeDirectory = "/home/${config.home.username}";
  home.packages = [ pkgs.xss-lock hiDpiScript ];
  programs.atuin.package = atuinModule.atuinPackage;
  programs.atuin.settings.secrets_filter = false;

  services.xps-desktop.enable = true;
  services.restic-backup = {
    enable = true;
    paths = [ config.home.homeDirectory "/vault" ];
    requiredMounts = [ "/vault" ];
    protectedSources = [
      {
        name = "tailscale-global";
        path = "${config.home.homeDirectory}/.local/state/liqwid-infra/global";
        directory = true;
        ignore = [ "tailscaled.log" "dns-cache" "derpmap.cached.json" ];
      }
      {
        name = "luks-header";
        path = "${config.home.homeDirectory}/Desktop/luks-header.img";
      }
      {
        name = "onebus-postgis";
        path = "${config.home.homeDirectory}/Projects/onebus/data/postgis";
        directory = true;
        stoppedContainer = "onebus-postgis";
      }
    ];
  };

  home.pointerCursor = {
    package = pkgs.kdePackages.breeze;
    name = "breeze_cursors";
    size = 48;
    x11.enable = true;
  };
  home.sessionVariables.QT_ENABLE_HIGHDPI_SCALING = "1";
  xresources.properties."Xft.dpi" = 192;
  services.xsettingsd = {
    enable = true;
    settings = {
      "Gdk/WindowScalingFactor" = 2;
      "Gdk/UnscaledDPI" = 96 * 1024;
      "Xft/DPI" = 192 * 1024;
      "Gtk/CursorThemeName" = "breeze_cursors";
      "Gtk/CursorThemeSize" = 48;
    };
  };
  # Match Ubuntu's running systemd manager.
  systemd.user.systemctlPath = "/usr/bin/systemctl";
  services.dunst = {
    enable = true;
    settings = {
      global = {
        font = "Noto Sans 10";
        scale = 2;
        width = 300;
        offset = "(10,50)";
        padding = 8;
        horizontal_padding = 8;
        frame_width = 2;
        min_icon_size = 32;
        max_icon_size = 32;
      };
      urgency_normal.timeout = 8;
    };
  };
  services.ssh-agent.enable = true;
  home.file.".xsessionrc".text = ''
    . "${config.home.profileDirectory}/etc/profile.d/hm-session-vars.sh"
    # Toolkit overrides would multiply the shared X11 scaling policy.
    unset GDK_SCALE GDK_DPI_SCALE QT_SCALE_FACTOR QT_SCREEN_SCALE_FACTORS QT_FONT_DPI
    ${hiDpiScript}/bin/xps-apply-hidpi
  '';
  home.activation.applyHiDpi = lib.hm.dag.entryAfter [ "reloadSystemd" ] ''
    if [ -n "''${DISPLAY:-}" ]; then
      ${hiDpiScript}/bin/xps-apply-hidpi
      ${config.systemd.user.systemctlPath} --user restart xsettingsd.service
    fi
  '';
}
