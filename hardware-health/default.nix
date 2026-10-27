{ config, lib, pkgs, hostName, ... }:
let
  cfg = config.services.hardware-health;
  darwin = pkgs.stdenv.hostPlatform.isDarwin;
  settings = pkgs.writeText "hardware-health.json" (builtins.toJSON {
    host = hostName;
    platform = if darwin then "darwin" else "linux";
    inherit (cfg) battery devices sudoSmartctl thresholds remoteReports;
    smartctl = if darwin then "${pkgs.smartmontools}/bin/smartctl" else cfg.linuxSmartctl;
    notifySend = if darwin then null else "${pkgs.libnotify}/bin/notify-send";
    stateDirectory = "${config.xdg.stateHome}/hardware-health";
  });
  command = pkgs.writeShellScriptBin "hardware-health" ''
    exec ${pkgs.python3}/bin/python3 -I ${./monitor.py} --config ${settings} "$@"
  '';
  accessSettings = pkgs.writeText "hardware-health-access.json" (builtins.toJSON {
    user = config.home.username;
    smartctl = cfg.linuxSmartctl;
    devices = cfg.devices;
  });
  installer = pkgs.writeShellScriptBin "install-hardware-health-access" ''
    exec /usr/bin/sudo /usr/bin/python3 -I ${./install-access.py} --config ${accessSettings} "$@"
  '';
  limit = default: description: lib.mkOption {
    type = lib.types.ints.positive; inherit default description;
  };
in {
  options.services.hardware-health = {
    enable = lib.mkEnableOption "monthly battery and NVMe health trends";
    battery = lib.mkOption { type = lib.types.bool; default = true; };
    devices = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = "Explicit internal NVMe controllers; external/removable drives are not scanned.";
    };
    linuxSmartctl = lib.mkOption { type = lib.types.str; default = "/usr/sbin/smartctl"; };
    sudoSmartctl = lib.mkOption { type = lib.types.bool; default = !darwin; };
    thresholds = {
      batteryMonthlyPoints = limit 5 "Battery capacity percentage-point loss within 45 days.";
      batteryQuarterlyPoints = limit 10 "Battery capacity percentage-point loss within 105 days.";
      ssdMonthlyPoints = limit 5 "SSD endurance percentage-point consumption within 45 days.";
      ssdQuarterlyPoints = limit 10 "SSD endurance percentage-point consumption within 105 days.";
      ssdSparePoints = limit 1 "Reduction in SSD spare capacity since the previous reading.";
      ssdErrorEntries = limit 100 "Increase in controller error-log count; media errors always alert on any increase.";
    };
    remoteReports = lib.mkOption {
      type = lib.types.listOf (lib.types.submodule {
        options = {
          name = lib.mkOption { type = lib.types.str; };
          host = lib.mkOption { type = lib.types.str; };
          port = lib.mkOption { type = lib.types.port; default = 22; };
          command = lib.mkOption { type = lib.types.str; };
        };
      });
      default = [ ];
      description = "Saved health reports fetched read-only over SSH and notified on this desktop.";
    };
  };
  config = lib.mkIf cfg.enable (lib.mkMerge [
    {
      assertions = [ {
        assertion = cfg.battery || cfg.devices != [ ];
        message = "Enable at least one hardware health source.";
      } {
        assertion = lib.all (device: builtins.match (if darwin then "/dev/disk[0-9]+" else "/dev/nvme[0-9]+") device != null) cfg.devices;
        message = "Hardware health currently supports explicit whole NVMe controllers only.";
      } {
        assertion = !darwin || !cfg.sudoSmartctl;
        message = "macOS SMART queries are unprivileged; no sudo policy is provided.";
      } {
        assertion = lib.all (remote: builtins.match "[a-zA-Z0-9._@:-]+" remote.host != null
          && builtins.match "/[a-zA-Z0-9/_.-]+" remote.command != null) cfg.remoteReports;
        message = "Remote hardware reports need a literal SSH destination and absolute command path.";
      } ];
      home.packages = [ command ];
      home.file.".local/bin/hardware-health".source = "${command}/bin/hardware-health";
      home.sessionPath = [ "${config.home.homeDirectory}/.local/bin" ];
    }
    (lib.mkIf (!darwin && cfg.sudoSmartctl && cfg.devices != [ ]) {
      home.file.".local/bin/install-hardware-health-access".source = "${installer}/bin/install-hardware-health-access";
    })
    (lib.mkIf (!darwin) {
      systemd.user.services.hardware-health = {
        Unit.Description = "Monthly battery/NVMe reading and pending health notifications";
        Service = {
          Type = "oneshot";
          ExecStart = "${command}/bin/hardware-health --scheduled";
          UMask = "0077";
          Nice = 10;
          TimeoutStartSec = "3m";
        };
      };
      systemd.user.timers.hardware-health = {
        Unit.Description = "Retry monthly hardware reading and pending notifications while awake";
        Timer = {
          OnCalendar = "*-*-* 10:00:00";
          OnStartupSec = "2m";
          RandomizedDelaySec = "5m";
          Persistent = true;
        };
        Install.WantedBy = [ "timers.target" ];
      };
    })
    (lib.mkIf darwin {
      launchd.agents.hardware-health = {
        enable = true;
        config = {
          ProgramArguments = [ "${command}/bin/hardware-health" "--scheduled" ];
          StartCalendarInterval = { Hour = 10; Minute = 7; };
          RunAtLoad = true;
          ProcessType = "Background";
          LowPriorityIO = true;
          Nice = 10;
          Umask = 63;
          StandardOutPath = "${config.home.homeDirectory}/Library/Logs/hardware-health.log";
          StandardErrorPath = "${config.home.homeDirectory}/Library/Logs/hardware-health-error.log";
        };
      };
      home.file."Library/Logs/.hardware-health-directory".text = "";
    })
  ]);
}
