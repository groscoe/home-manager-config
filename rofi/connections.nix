{ config, lib, pkgs, ... }:

let
  menuRofi = config.programs.rofi.finalPackage;
  bluetoothMenu = pkgs.writeShellApplication {
    name = "rofi-bluetooth";
    runtimeInputs = [
      menuRofi
      pkgs.coreutils
      pkgs.gnugrep
      pkgs.procps
      pkgs.util-linux
    ];
    text = ''
      # bluetoothctl's status labels are parsed by the upstream menu.
      export LC_ALL=C.UTF-8
      exec ${pkgs.rofi-bluetooth}/bin/rofi-bluetooth -i "$@"
    '';
  };
  wifiMenu = pkgs.writeShellApplication {
    name = "rofi-wifi";
    runtimeInputs = [ menuRofi pkgs.networkmanager pkgs.libnotify ];
    text = ''
      exec ${pkgs.networkmanager_dmenu}/bin/networkmanager_dmenu \
        --config ${lib.escapeShellArg "${config.xdg.configHome}/networkmanager-dmenu/config.ini"} "$@"
    '';
  };
  bluetoothDesktop = pkgs.makeDesktopItem {
    name = "rofi-bluetooth";
    desktopName = "Bluetooth";
    genericName = "Bluetooth connections in Rofi";
    comment = "Pair, connect and manage Bluetooth devices inside Rofi";
    exec = "${bluetoothMenu}/bin/rofi-bluetooth";
    icon = "bluetooth";
    terminal = false;
    categories = [ "Settings" "HardwareSettings" ];
    keywords = [ "bluetooth" "headphones" "pair" "connect" "rofi" ];
  };
  wifiDesktop = pkgs.makeDesktopItem {
    name = "rofi-wifi";
    desktopName = "Wi-Fi";
    genericName = "Wi-Fi connections in Rofi";
    comment = "Select wireless networks and manage connections inside Rofi";
    exec = "${wifiMenu}/bin/rofi-wifi";
    icon = "network-wireless";
    terminal = false;
    categories = [ "Settings" "Network" ];
    keywords = [ "wifi" "wi-fi" "wireless" "network" "internet" "rofi" ];
  };
in
{
  config = lib.mkIf (pkgs.stdenv.hostPlatform.isLinux && config.programs.rofi.enable) {
    # Super+Space uses combi; include desktop entries as well as commands/windows.
    programs.rofi.extraConfig.combi-modes = "drun,run,window";

    # These are menu scripts, rather than compiled Rofi plugins.
    home.packages = [ bluetoothMenu wifiMenu bluetoothDesktop wifiDesktop ];

    # Existing display-manager sessions may omit the profile from XDG_DATA_DIRS.
    # Link the same entries into the standard per-user application directory.
    xdg.dataFile = {
      "applications/rofi-bluetooth.desktop".source =
        "${bluetoothDesktop}/share/applications/rofi-bluetooth.desktop";
      "applications/rofi-wifi.desktop".source =
        "${wifiDesktop}/share/applications/rofi-wifi.desktop";
    };

    xdg.configFile."networkmanager-dmenu/config.ini".text = ''
      [dmenu]
      dmenu_command = ${menuRofi}/bin/rofi -i
      prompt = Wi-Fi
      compact = True
      highlight = True
      list_saved = False
      wifi_chars = ▂▄▆█
      format = {name}  {sec}  {bars}

      [dmenu_passphrase]
      obscure = True

      [editor]
      terminal = ${pkgs.alacritty}/bin/alacritty
      gui_if_available = False

      [nmdm]
      rescan_delay = 5
      show_notifications = True
    '';
  };
}
