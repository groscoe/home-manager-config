{ config, pkgs, lib, ... }:
let
  scan = pkgs.writeShellScriptBin "xps-clamav-scan" ''
    exec /usr/bin/python3 ${./scan.py} "$@"
  '';
in {
  config = lib.mkIf pkgs.stdenv.isLinux {
    home.packages = [ scan ];
    systemd.user.services.clamav-scan = {
      Unit.Description = "Daily antivirus scan of Downloads, Desktop and encrypted vault";
      Service = {
        Type = "oneshot";
        ExecStart = "${scan}/bin/xps-clamav-scan";
        Nice = 15;
        IOSchedulingClass = "idle";
        CPUWeight = 10;
        IOWeight = 10;
        UMask = "0077";
        NoNewPrivileges = true;
        # Long scans are allowed; systemd and a lock prevent overlap.
        TimeoutStartSec = "infinity";
        TimeoutStopSec = 45;
      };
    };
    systemd.user.timers.clamav-scan = {
      Unit.Description = "Check hourly for a daily antivirus scan while awake and on AC";
      Timer = {
        OnCalendar = "hourly";
        RandomizedDelaySec = "10m";
        Persistent = true;
        Unit = "clamav-scan.service";
      };
      Install.WantedBy = [ "timers.target" ];
    };
  };
}
