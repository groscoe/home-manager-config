{ lib, runCommand, python3, stdenv, pkg-config, xvfb-run, xorg, writeText, tmux, physical, virtual }:
let
  describe = profile:
    let cfg = profile.config;
        codium = lib.findFirst (p: lib.getName p == "vscodium") null cfg.home.packages;
        keyboard = lib.findFirst (p: lib.getName p == "xps-x-settings") null cfg.home.packages;
    in {
      hardware = cfg.personal.hardware;
      graphicsWrapper = cfg.targets.genericLinux.nixGL.defaultWrapper;
      codium = "${codium}/bin/codium";
      codiumVersion = codium.version;
      bar = "${cfg.home.file.".config/polybar".source}/material/config.ini";
      keyboard = "${keyboard}/bin/xps-x-settings";
      tmuxConfig = toString cfg.home.file.".config/tmux/client-prefix.conf".source;
      dpi = cfg.xresources.properties."Xft.dpi";
      cursorSize = cfg.home.pointerCursor.size;
      xsettings = cfg.services.xsettingsd.settings;
      health = cfg.services.hardware-health.enable;
      healthDevices = cfg.services.hardware-health.devices;
      vnc = cfg.services.xps-desktop.enable;
      backup = cfg.services.restic-backup.enable;
      scan = builtins.hasAttr "clamav-scan" cfg.systemd.user.timers;
    };
  settings = writeText "hardware-profile-check.json" (builtins.toJSON {
    physical = describe physical;
    virtual = describe virtual;
  });
in runCommand "hardware-profile-contracts" {
  nativeBuildInputs = [ python3 stdenv.cc pkg-config xvfb-run tmux ];
  buildInputs = [ xorg.libX11 xorg.libXrandr ];
} ''
  export HOME="$TMPDIR/home"
  mkdir -p "$HOME"
  $CC -O2 -Wall -Wextra ${lib.escapeShellArg "-DXPS_PANEL_OUTPUT=\"screen\""} \
    ${../xps-desktop/panel-gamma.c} -o panel-screen $(pkg-config --cflags --libs x11 xrandr)
  $CC -O2 -Wall -Wextra ${lib.escapeShellArg "-DXPS_PANEL_OUTPUT=\"missing-panel\""} \
    ${../xps-desktop/panel-gamma.c} -o panel-missing $(pkg-config --cflags --libs x11 xrandr)
  xvfb-run -a --server-args="-screen 0 1280x1024x24 -noreset" \
    ${python3}/bin/python3 -I ${./check.py} ${settings} "$PWD/panel-screen" "$PWD/panel-missing" > "$out"
''
