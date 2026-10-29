{
  config,
  lib,
  pkgs,
  ...
}:
let
  c = builtins.fromJSON (builtins.readFile ./palette.json);
  profile = config.home.profileDirectory;
  rofi = "${config.programs.rofi.finalPackage}/bin/rofi";
  palette = pkgs.writeText "lake-bled-palette.json" (builtins.toJSON c);
  python = pkgs.python3.withPackages (ps: [ ps.pygobject3 ]);
  shortcuts = pkgs.stdenvNoCC.mkDerivation {
    pname = "xps-shortcuts";
    version = "2";
    dontUnpack = true;
    nativeBuildInputs = [
      pkgs.wrapGAppsHook3
      pkgs.makeWrapper
      pkgs.gobject-introspection
    ];
    buildInputs = [ pkgs.gtk3 ];
    installPhase = ''
      mkdir -p "$out/bin" "$out/share/xps-shortcuts"
      cp ${./shortcuts.py} "$out/share/xps-shortcuts/shortcuts.py"
      makeWrapper ${python}/bin/python3 "$out/bin/xps-shortcuts" \
        --add-flags "-I $out/share/xps-shortcuts/shortcuts.py --palette ${palette} --tmux ${pkgs.tmux}/bin/tmux"
    '';
    doInstallCheck = true;
    nativeInstallCheckInputs = [ pkgs.xvfb-run ];
    installCheckPhase = ''
      "$out/bin/xps-shortcuts" --check-runtime
      export GDK_BACKEND=x11
      export FONTCONFIG_FILE=${
        pkgs.makeFontsConf {
          fontDirectories = [
            pkgs.noto-fonts
            pkgs.source-code-pro
          ];
        }
      }
      xvfb-run -a --server-args="-screen 0 3840x2400x24" \
        "$out/bin/xps-shortcuts" --check-ui --config ${pkgs.writeText "shortcuts-test-i3.conf" i3Config}
    '';
  };
  shortcutDesktop = pkgs.makeDesktopItem {
    name = "xps-shortcuts";
    desktopName = "Keyboard shortcuts";
    genericName = "Desktop, tmux and selection controls";
    comment = "Search desktop, tmux, copy mode and advanced shortcuts with XPS and Mac/VNC key labels";
    exec = "${shortcuts}/bin/xps-shortcuts";
    icon = "preferences-desktop-keyboard-shortcuts";
    terminal = false;
    categories = [ "Utility" ];
    keywords = [
      "keyboard"
      "shortcuts"
      "help"
      "i3"
      "tmux"
    ];
  };
  menuConfig = pkgs.writeText "xps-session-menu.json" (
    builtins.toJSON {
      inherit rofi;
      i3msg = "${pkgs.i3}/bin/i3-msg";
      systemctl = "/usr/bin/systemctl";
      locker = "/usr/bin/i3lock";
    }
  );
  sessionMenu = pkgs.writeShellScriptBin "xps-session-menu" ''
    exec ${pkgs.python3}/bin/python3 -I ${./session-menu.py} ${menuConfig}
  '';
  wallpaper = ./lake-bled-sunrise.jpg;
  applyWallpaper = pkgs.writeShellScriptBin "xps-apply-wallpaper" ''
    set -eu
    [ -n "''${DISPLAY:-}" ] || exit 0
    exec ${pkgs.feh}/bin/feh --no-fehbg --bg-fill ${wallpaper}
  '';
  baseI3 = builtins.readFile ../../../i3/config/i3/config;
  i3Config =
    lib.replaceStrings
      [
        "@xpsPolybar@"
        "@xpsPicom@"
        "@xpsXSettings@"
        "hide_edge_borders both"
        "set $bg-color            #2f343f"
        "set $inactive-bg-color   #2f343f"
        "set $text-color          #f3f4f5"
        "set $inactive-text-color #676e7d"
        "set $urgent-bg-color     #e53935"
        "set $indicator-color     #a0a0a0"
        "client.focused          $bg-color          $bg-color"
        "for_window [class=\".*\"] border pixel 0"
        "exec --no-startup-id \"feh --bg-scale ~/Pictures/Wallpapers/japan-temple-ultrawide.jpg\""
      ]
      [
        "${profile}/bin/xps-start-polybar"
        "${profile}/bin/xps-start-picom"
        "${profile}/bin/xps-x-settings"
        "hide_edge_borders none"
        "set $bg-color            ${c.panel}"
        "set $inactive-bg-color   ${c.edge}"
        "set $text-color          ${c.foreground}"
        "set $inactive-text-color ${c.muted}"
        "set $urgent-bg-color     ${c.red}"
        "set $indicator-color     ${c.accent}"
        "client.focused          ${c.accent}          $bg-color"
        "for_window [class=\".*\"] border pixel 4"
        "exec_always --no-startup-id ${applyWallpaper}/bin/xps-apply-wallpaper"
      ]
      baseI3
    + ''

      # The reference is a normal, non-modal window; it never runs listed actions.
      for_window [class="XpsShortcuts"] floating enable, resize set 1800 px 1720 px, move position center

      # Use the slash symbol on ABNT-2 and Mac/VNC layouts, regardless of keycode.
      bindsym --release $mod+Shift+slash exec --no-startup-id ${profile}/bin/xps-command-search
    '';
  alacritty = builtins.fromTOML (
    builtins.readFile ../../../terminals/config/alacritty/alacritty.toml
  );
  ansi = {
    black = c.raised;
    red = c.red;
    green = c.green;
    yellow = c.yellow;
    blue = c.blue;
    magenta = c.lavender;
    cyan = c.cyan;
    white = c.foreground;
  };
  tmuxTheme = pkgs.writeText "tmux-lake-bled.conf" ''
    # Appearance only: preserve client-specific prefixes, copy bindings and hooks.
    set -g status-style "bg=${c.raised},fg=${c.muted}"
    set -g status-left "#[fg=${c.accent}] #S #[default] "
    set -g status-left-length 40
    set -g status-right "#[fg=${c.muted}] #H · %H:%M "
    set -g status-right-length 60
    setw -g window-status-style "fg=${c.muted},bg=${c.raised}"
    setw -g window-status-current-style "fg=${c.accent},bg=${c.selected}"
    setw -g window-status-format " #I:#W "
    setw -g window-status-current-format " #I:#W* "
    set -g message-style "fg=${c.foreground},bg=${c.panel}"
    setw -g mode-style "fg=${c.foreground},bg=${c.selected}"
    set -g pane-border-style "fg=${c.edge}"
    set -g pane-active-border-style "fg=${c.accent}"
  '';
  rofiTheme = pkgs.writeText "lake-bled.rasi" ''
    * {
      background-color: ${c.panel};
      text-color: ${c.foreground};
      border-color: ${c.edge};
      selected-normal-background: ${c.selected};
      selected-normal-foreground: ${c.foreground};
      normal-background: ${c.panel};
      normal-foreground: ${c.foreground};
      alternate-normal-background: ${c.panel};
      alternate-normal-foreground: ${c.foreground};
      spacing: 12px;
    }
    window { width: 1120px; location: center; anchor: center; padding: 24px; border: 2px; border-radius: 16px; }
    mainbox { spacing: 18px; }
    inputbar { children: [ prompt, entry ]; padding: 18px; spacing: 16px; background-color: ${c.background}; border: 1px; border-radius: 8px; }
    prompt { text-color: ${c.accent}; background-color: inherit; }
    entry { placeholder: "Find an app or connection…"; background-color: inherit; }
    listview { lines: 8; columns: 1; fixed-height: false; scrollbar: false; spacing: 6px; border: 0px; }
    element { padding: 16px; spacing: 18px; border: 0px 0px 0px 4px; border-color: transparent; border-radius: 8px; }
    element normal.normal { background-color: ${c.panel}; text-color: ${c.foreground}; }
    element alternate.normal { background-color: ${c.panel}; text-color: ${c.foreground}; }
    element selected.normal { background-color: ${c.selected}; text-color: ${c.foreground}; border-color: ${c.accent}; }
    element selected.urgent { background-color: ${c.selected}; text-color: ${c.red}; border-color: ${c.red}; }
    element-icon { size: 32px; background-color: inherit; }
    element-text { background-color: inherit; text-color: inherit; vertical-align: 0.5; }
    message { padding: 12px; border: 1px 0px 0px; border-color: ${c.edge}; }
    textbox { text-color: ${c.muted}; background-color: inherit; }
    mode-switcher { spacing: 8px; }
    button { padding: 10px; border-radius: 4px; }
    button selected { background-color: ${c.selected}; text-color: ${c.accent}; }
  '';
  barVariables = c // {
    launcher = "${rofi} -show combi";
    wifi = "${profile}/bin/rofi-wifi";
    shortcuts = "${shortcuts}/bin/xps-shortcuts";
    notices = "${config.services.dunst.package}/bin/dunstctl";
    power = "${sessionMenu}/bin/xps-session-menu";
    audio = "${pkgs.pavucontrol}/bin/pavucontrol";
  };
  barConfig = pkgs.replaceVars ./polybar.ini.in (
    lib.filterAttrs (
      name: _: lib.hasInfix "@${name}@" (builtins.readFile ./polybar.ini.in)
    ) barVariables
  );
  # Keep the other legacy bar assets available, without changing shared files.
  polybarFiles = pkgs.runCommand "polybar-lake-bled" { } ''
    cp -R ${../../../polybar/config/polybar} "$out"
    chmod -R u+w "$out"
    cp ${barConfig} "$out/material/config.ini"
  '';
in
{
  home.packages = [
    shortcuts
    shortcutDesktop
    applyWallpaper
    sessionMenu
    pkgs.noto-fonts
    pkgs.adwaita-icon-theme
  ];
  home.file = {
    ".tmux.conf".source = lib.mkForce (
      pkgs.writeText "tmux-xps.conf" (
        builtins.readFile ../../../terminals/tmux.conf + "\nsource-file ${tmuxTheme}\n"
      )
    );
    ".config/i3/config".source = lib.mkForce (pkgs.writeText "i3-lake-bled.conf" i3Config);
    ".config/polybar".source = lib.mkForce polybarFiles;
    ".config/alacritty/alacritty.toml".source = lib.mkForce (
      (pkgs.formats.toml { }).generate "alacritty-lake-bled.toml" (
        lib.recursiveUpdate alacritty {
          colors = {
            primary = {
              background = c.background;
              foreground = c.foreground;
              dim_foreground = c.muted;
            };
            normal = ansi;
            bright = ansi // {
              black = c.edge;
              white = "#fff3ec";
            };
            dim = ansi // {
              white = c.muted;
            };
            cursor = {
              cursor = c.accent;
              text = c.background;
            };
            vi_mode_cursor = {
              cursor = c.lavender;
              text = c.background;
            };
            selection = {
              background = c.selected;
              text = c.foreground;
            };
            search.matches = {
              background = c.lavender;
              foreground = c.background;
            };
            footer_bar = {
              background = c.raised;
              foreground = c.foreground;
            };
          };
          window.opacity = 1.0;
        }
      )
    );
    "Pictures/Wallpapers/lake-bled-sunrise.jpg".source = wallpaper;
  };
  xdg.dataFile."applications/xps-shortcuts.desktop".source =
    "${shortcutDesktop}/share/applications/xps-shortcuts.desktop";
  programs.rofi = {
    theme = lib.mkForce "${rofiTheme}";
    font = lib.mkForce "Noto Sans 12";
    extraConfig = {
      dpi = config.xresources.properties."Xft.dpi";
      eh = 2;
      combi-display-format = "{text}";
      show-icons = true;
      icon-theme = "Adwaita";
      display-combi = "Applications";
      drun-display-format = "{name}\\n<span size='small' foreground='${c.muted}'>{generic}</span>";
    };
  };
  services.dunst.settings = {
    global = {
      font = lib.mkForce "Noto Sans 10";
      width = lib.mkForce 360;
      offset = lib.mkForce "(14,28)";
      padding = lib.mkForce 14;
      horizontal_padding = lib.mkForce 14;
      frame_width = lib.mkForce 2;
      corner_radius = 8;
      separator_color = c.edge;
      highlight = c.accent;
      background = c.panel;
      foreground = c.foreground;
    };
    urgency_low = {
      background = c.panel;
      foreground = c.foreground;
      frame_color = c.green;
      timeout = 5;
    };
    urgency_normal = {
      background = c.panel;
      foreground = c.foreground;
      frame_color = c.lavender;
      timeout = lib.mkForce 8;
    };
    urgency_critical = {
      background = c.panel;
      foreground = c.foreground;
      frame_color = c.red;
      timeout = 0;
    };
  };
  home.activation.applyLakeBled = lib.hm.dag.entryAfter [ "reloadSystemd" "xpsDesktopDisplay" ] ''
    if [ -n "''${DISPLAY:-}" ] && ${pkgs.i3}/bin/i3-msg -t get_version >/dev/null 2>&1; then
      ${pkgs.i3}/bin/i3-msg reload
      ${applyWallpaper}/bin/xps-apply-wallpaper
      ${config.systemd.user.systemctlPath} --user restart polybar.service dunst.service
      if ${pkgs.tmux}/bin/tmux list-sessions >/dev/null 2>&1; then
        ${pkgs.tmux}/bin/tmux source-file ${tmuxTheme}
      fi
      if ${config.systemd.user.systemctlPath} --user is-active --quiet xps-desktop.service; then
        ${profile}/bin/xps-desktop-control refresh-display
      fi
    fi
  '';
}
