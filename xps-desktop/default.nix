{ config, lib, pkgs, ... }:
let
  cfg = config.services.xps-desktop;
  linux = pkgs.stdenv.hostPlatform.isLinux;
  darwin = pkgs.stdenv.hostPlatform.isDarwin;
  python = pkgs.python3;
  panelGamma = pkgs.stdenv.mkDerivation {
    pname = "xps-desktop-panel-gamma";
    version = "1";
    dontUnpack = true;
    nativeBuildInputs = [ pkgs.pkg-config ];
    buildInputs = [ pkgs.xorg.libX11 pkgs.xorg.libXrandr ];
    buildPhase = ''
      $CC -O2 -Wall -Wextra ${./panel-gamma.c} -o xps-desktop-panel-gamma $(pkg-config --cflags --libs x11 xrandr)
    '';
    installPhase = ''
      install -Dm755 xps-desktop-panel-gamma "$out/bin/xps-desktop-panel-gamma"
    '';
  };
  serverConfig = pkgs.writeText "xps-desktop-server.json" (builtins.toJSON {
    vnc = "${pkgs.tigervnc}/bin/x0vncserver";
    vncpasswd = "${pkgs.tigervnc}/bin/vncpasswd";
    passwordFile = "${config.xdg.stateHome}/xps-desktop/passwd";
    systemctl = config.systemd.user.systemctlPath;
    xset = "/usr/bin/xset";
    dbusSend = "/usr/bin/dbus-send";
    backlightDevice = "intel_backlight";
    panelGamma = "${panelGamma}/bin/xps-desktop-panel-gamma";
  });
  server = pkgs.writeShellScriptBin "xps-desktop-control" ''
    exec ${python}/bin/python3 -I ${./server.py} ${serverConfig} "$@"
  '';
  backlightAccessInstaller = pkgs.writeShellScriptBin "install-xps-backlight-access" ''
    exec /usr/bin/sudo /usr/bin/python3 -I ${./install-backlight-access.py} --user ${lib.escapeShellArg config.home.username} "$@"
  '';
  clientConfig = pkgs.writeText "xps-desktop-client.json" (builtins.toJSON {
    inherit (cfg) sshHost sshPort localPort;
    remoteControl = "${cfg.remoteHome}/.nix-profile/bin/xps-desktop-control";
    remoteSocket = "/run/user/${toString cfg.remoteUid}/xps-desktop/desktop.sock";
    ssh = "/usr/bin/ssh";
    open = "/usr/bin/open";
    viewer = "/System/Applications/Utilities/Screen Sharing.app";
  });
  client = pkgs.writeShellScriptBin "xps-desktop" ''
    exec ${python}/bin/python3 -I ${./client.py} ${clientConfig} "$@"
  '';
  app = pkgs.runCommand "xps-desktop-macos-app" {} ''
    app="$out/Applications/XPS Desktop.app/Contents"
    mkdir -p "$app/MacOS"
    cat > "$app/Info.plist" <<'EOF'
    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0"><dict>
      <key>CFBundleIdentifier</key><string>org.groscoe.xps-desktop</string>
      <key>CFBundleName</key><string>XPS Desktop</string>
      <key>CFBundleDisplayName</key><string>XPS Desktop</string>
      <key>CFBundleExecutable</key><string>XPSDesktop</string>
      <key>CFBundlePackageType</key><string>APPL</string>
      <key>CFBundleVersion</key><string>1</string>
      <key>LSUIElement</key><true/>
      <key>NSHighResolutionCapable</key><true/>
    </dict></plist>
    EOF
    cat > "$app/MacOS/XPSDesktop" <<'EOF'
    #!${pkgs.runtimeShell}
    exec ${client}/bin/xps-desktop --gui
    EOF
    chmod +x "$app/MacOS/XPSDesktop"
  '';
in {
  options.services.xps-desktop = {
    enable = lib.mkEnableOption "SSH-only sharing of xps's existing i3 desktop";
    sshHost = lib.mkOption { type = lib.types.str; default = "192.168.1.2"; };
    sshPort = lib.mkOption { type = lib.types.port; default = 2222; };
    localPort = lib.mkOption { type = lib.types.port; default = 59320; };
    remoteUid = lib.mkOption { type = lib.types.ints.unsigned; default = 1000; };
    remoteHome = lib.mkOption { type = lib.types.str; default = "/home/groscoe"; };
  };
  config = lib.mkIf cfg.enable (lib.mkMerge [
    (lib.mkIf linux {
      home.packages = [ server pkgs.tigervnc backlightAccessInstaller ];
      home.activation.xpsDesktopDisplay = lib.hm.dag.entryAfter [ "applyHiDpi" "reloadSystemd" ] ''
        if ${config.systemd.user.systemctlPath} --user is-active --quiet xps-desktop.service; then
          ${server}/bin/xps-desktop-control refresh-display
        fi
      '';
      systemd.user.services.xps-desktop = {
        Unit.Description = "Share the existing i3 session through a private SSH-accessible VNC socket";
        Service = {
          Type = "simple";
          ExecStart = "${server}/bin/xps-desktop-control serve";
          ExecStopPost = "${server}/bin/xps-desktop-control restore-display";
          RuntimeDirectory = "xps-desktop";
          RuntimeDirectoryMode = "0700";
          UMask = "0077";
          NoNewPrivileges = true;
          RestrictAddressFamilies = [ "AF_UNIX" ];
          Restart = "no";
          TimeoutStopSec = 30;
          Nice = 5;
        };
        # Started on demand by the Mac launcher, after an i3 login exists.
      };
    })
    (lib.mkIf darwin {
      home.packages = [ client ];
      home.file."Applications/XPS Desktop.app".source = "${app}/Applications/XPS Desktop.app";
    })
  ]);
}
