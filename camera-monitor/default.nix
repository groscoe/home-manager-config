{ config, lib, pkgs, ... }:
let
  cfg = config.services.camera-monitor;
  engine = pkgs.callPackage ./ebpf/ebpf.nix { };
  settings = pkgs.writeText "camera-monitor.json" (builtins.toJSON {
    rofi = "${config.programs.rofi.finalPackage}/bin/rofi";
    controller = config.personal.hardware.cameraController;
    notify = "${pkgs.libnotify}/bin/notify-send";
  });
  package = pkgs.writeShellScriptBin "camera-monitor" ''
    exec ${pkgs.python3}/bin/python3 -I ${./monitor.py} --config ${settings} "$@"
  '';
  installer = pkgs.writeShellScriptBin "install-camera-monitor-access" ''
    exec /usr/bin/sudo -- /usr/bin/python3 -I ${./install-access.py} \
      --source ${./monitor.py} --collector ${./collector.py} --engine ${engine} --user ${lib.escapeShellArg config.home.username} "$@"
  '';
  controllerConfig = pkgs.writeText "camera-controller.json" (builtins.toJSON config.personal.hardware.cameraController);
  controlsInstaller = pkgs.writeShellScriptBin "install-camera-controls" ''
    exec /usr/bin/sudo -- /usr/bin/python3 -I ${./install-controls.py} \
      --control ${./control.py} --config ${controllerConfig} --monitor ${./monitor.py} \
      --test ${./test-controls.py} --user ${lib.escapeShellArg config.home.username} "$@"
  '';
in {
  options.services.camera-monitor.enable = lib.mkEnableOption "read-only camera handle monitoring";
  config = lib.mkIf cfg.enable {
    home.packages = [ package installer ] ++ lib.optional (config.personal.hardware.cameraController != null) controlsInstaller;
    systemd.user.services.camera-monitor = {
      Unit = {
        Description = "Camera access indicator (metadata only)";
      };
      Service = {
        ExecStart = "${package}/bin/camera-monitor watch";
        Restart = "on-failure";
        RestartSec = 3;
        UMask = "0077";
        NoNewPrivileges = true;
      };
      Install.WantedBy = [ "default.target" ];
    };
    xdg.desktopEntries.camera-monitor = {
      name = "Camera access";
      genericName = "Webcam process details";
      exec = "${package}/bin/camera-monitor menu";
      icon = "camera-web";
      categories = [ "Utility" ];
      terminal = false;
    };
  };
}
