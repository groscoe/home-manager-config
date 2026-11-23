{ config, pkgs, lib, ... }:
let
  settings = pkgs.writeText "clamav-scan-policy.json" (builtins.toJSON {
    clamscan = "/usr/bin/clamscan";
    notify = "${pkgs.libnotify}/bin/notify-send";
    roots = [ "${config.home.homeDirectory}/Downloads" "${config.home.homeDirectory}/Desktop" "/vault" ];
    state_directory = "/vault/.clamav-scan";
    inventory_seconds = 120;
    recheck_days = 7;
    retain_reports = 14;
    daily = {
      max_file_mib = 256;
      max_scan_mib = 512;
      file_seconds = 120;
      container_files = 10000;
      max_files = 20000;
      input_mib = 4096;
      batch_size = 512;
      job_seconds = 2700;
    };
    rescan = {
      max_file_mib = 512;
      max_scan_mib = 1024;
      file_seconds = 600;
      container_files = 20000;
      max_files = 4;
      batch_size = 1;
      max_attempts = 2;
      retry_hours = 6;
      job_seconds = 2700;
    };
  });
  scan = pkgs.writeShellScriptBin "xps-clamav-scan" ''
    exec ${pkgs.python3}/bin/python3 -I ${./scan.py} --config ${settings} "$@"
  '';
  safeguards = {
    Type = "oneshot";
    Nice = 15;
    IOSchedulingClass = "idle";
    CPUWeight = 10;
    CPUQuota = "25%";
    IOWeight = 10;
    MemoryHigh = "1536M";
    MemoryMax = "2G";
    UMask = "0077";
    NoNewPrivileges = true;
    TimeoutStartSec = "50min";
    TimeoutStopSec = 30;
  };
in {
  config = lib.mkIf pkgs.stdenv.isLinux {
    home.packages = [ scan ];
    systemd.user.services = {
      clamav-scan = {
        Unit.Description = "Bounded daily incremental antivirus scan on AC";
        Service = safeguards // { ExecStart = "${scan}/bin/xps-clamav-scan"; };
      };
      clamav-document-rescan = {
        Unit.Description = "Bounded queue of documents not fully scanned by ClamAV";
        Service = safeguards // { ExecStart = "${scan}/bin/xps-clamav-scan --rescan"; };
      };
    };
    systemd.user.timers = {
      clamav-scan = {
        Unit.Description = "Hourly AC check for a bounded daily antivirus pass";
        Timer = {
          OnCalendar = "hourly";
          RandomizedDelaySec = "10m";
          Persistent = true;
          Unit = "clamav-scan.service";
        };
        Install.WantedBy = [ "timers.target" ];
      };
      clamav-document-rescan = {
        Unit.Description = "Retry a small bounded document batch every six hours on AC";
        Timer = {
          OnCalendar = "*-*-* 00,06,12,18:35:00";
          RandomizedDelaySec = "10m";
          Persistent = true;
          Unit = "clamav-document-rescan.service";
        };
        Install.WantedBy = [ "timers.target" ];
      };
    };
  };
}
