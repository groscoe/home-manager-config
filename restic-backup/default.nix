{ config, lib, pkgs, ... }:
let
  cfg = config.services.restic-backup;
  isDarwin = pkgs.stdenv.hostPlatform.isDarwin;
  protected = if cfg.protectedSources == [ ] then null else {
    directory = "/vault/.restic-protected";
    sources = map (source: source.path) cfg.protectedSources;
  };
  exportSettings = pkgs.writeText "restic-protected-export.json" (builtins.toJSON {
    user = config.home.username;
    directory = "/vault/.restic-protected";
    sources = cfg.protectedSources;
  });
  exportInstaller = pkgs.writeShellScriptBin "install-restic-backup-export" ''
    exec /usr/bin/sudo /usr/bin/python3 -I ${./install-protected-export.py} \
      --program ${./protected-export.py} --config ${exportSettings}
  '';
  scripts = pkgs.runCommand "restic-backup-scripts" { } ''
    mkdir -p "$out/lib/restic-backup"
    cp ${./runner.py} "$out/lib/restic-backup/runner.py"
    cp ${./backup-guard.py} "$out/lib/restic-backup/backup-guard.py"
    cp ${./home-manager-excludes.py} "$out/lib/restic-backup/home-manager-excludes.py"
  '';
  excludes = pkgs.writeText "restic-backup-excludes" (
    builtins.readFile ./excludes.txt
    + lib.optionalString (!isDarwin) ''
      ${config.home.homeDirectory}/Downloads/torrent
      ${config.home.homeDirectory}/.local/share/Trash
      /vault/lost+found
      /vault/.clamav-scan
    ''
    + lib.concatMapStringsSep "\n" (rule: rule) cfg.extraExcludes + "\n"
  );
  settings = pkgs.writeText "restic-backup.json" (builtins.toJSON {
    protectedExport = protected;
    inherit (cfg) paths environmentFile hostname requiredMounts intervalHours requireAC;
    thresholdGB = toString cfg.thresholdGB;
    stateDirectory = "${config.xdg.cacheHome}/restic-backup";
    homeDirectory = config.home.homeDirectory;
    restic = "${pkgs.restic}/bin/restic";
    bash = "${pkgs.bash}/bin/bash";
    notifySend = if isDarwin then null else "${pkgs.libnotify}/bin/notify-send";
    tags = [ (if isDarwin then "macos" else "linux") "home" "home-manager" ];
    excludeFiles = [ (toString excludes) ];
  });
  command = pkgs.writeShellScriptBin "restic-backup" ''
    exec ${pkgs.python3}/bin/python3 ${scripts}/lib/restic-backup/runner.py --config ${settings} "$@"
  '';
in {
  options.services.restic-backup = {
    enable = lib.mkEnableOption "guarded, automatic personal Restic backups";
    paths = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ config.home.homeDirectory ];
      description = "Absolute directories included in each snapshot.";
    };
    environmentFile = lib.mkOption {
      type = lib.types.str;
      default = "/etc/restic-env";
      description = "Existing private shell environment file. Credential values never enter the Nix store.";
    };
    hostname = lib.mkOption { type = lib.types.nullOr lib.types.str; default = null; };
    requiredMounts = lib.mkOption { type = lib.types.listOf lib.types.str; default = [ ]; };
    extraExcludes = lib.mkOption { type = lib.types.listOf lib.types.str; default = [ ]; };
    thresholdGB = lib.mkOption { type = lib.types.ints.unsigned; default = 20; };
    intervalHours = lib.mkOption { type = lib.types.ints.positive; default = 24; };
    requireAC = lib.mkOption { type = lib.types.bool; default = true; };
    protectedSources = lib.mkOption {
      type = lib.types.listOf lib.types.attrs;
      default = [ ];
      description = "Linux-only protected home files exported locally by a separately installed root service.";
    };
  };
  config = lib.mkIf cfg.enable (lib.mkMerge [
    {
      assertions = [ {
        assertion = cfg.paths != [ ] && lib.all (p: lib.hasPrefix "/" p) cfg.paths;
        message = "services.restic-backup.paths must contain absolute directories.";
      } {
        assertion = cfg.protectedSources == [ ] || (!isDarwin && builtins.elem "/vault" cfg.paths
          && lib.all (s: lib.hasPrefix "${config.home.homeDirectory}/" s.path
            && builtins.match "[a-z0-9-]+" s.name != null) cfg.protectedSources);
        message = "Protected exports require Linux, /vault coverage, and named sources inside the user's home.";
      } ];
      home.packages = [ command ];
      # Also available when activating only the Home Manager portion of an
      # existing nix-darwin system; its root-owned package profile is untouched.
      home.file.".local/bin/restic-backup".source = "${command}/bin/restic-backup";
      home.sessionPath = [ "${config.home.homeDirectory}/.local/bin" ];
    }
    (lib.mkIf (cfg.protectedSources != [ ]) {
      home.file.".local/bin/install-restic-backup-export".source = "${exportInstaller}/bin/install-restic-backup-export";
    })
    (lib.mkIf (!isDarwin) {
      systemd.user.services.restic-backup = {
        Unit.Description = "Guarded daily backup of configured personal directories";
        Service = {
          Type = "oneshot";
          ExecStart = "${command}/bin/restic-backup --scheduled";
          Nice = 15;
          IOSchedulingClass = "idle";
          CPUWeight = 10;
          IOWeight = 10;
          UMask = "0077";
          NoNewPrivileges = true;
          TimeoutStartSec = "infinity";
          TimeoutStopSec = 45;
          KillMode = "control-group";
        };
      };
      systemd.user.timers.restic-backup = {
        Unit.Description = "Retry hourly for a daily personal backup while awake/on AC";
        Timer = {
          OnCalendar = "hourly";
          RandomizedDelaySec = "10m";
          Persistent = true;
          Unit = "restic-backup.service";
        };
        Install.WantedBy = [ "timers.target" ];
      };
    })
    (lib.mkIf isDarwin {
      launchd.agents.restic-backup = {
        enable = true;
        config = {
          ProgramArguments = [ "${command}/bin/restic-backup" "--scheduled" ];
          StartCalendarInterval = { Minute = 17; };
          RunAtLoad = true;
          ProcessType = "Background";
          LowPriorityIO = true;
          Nice = 15;
          Umask = 63;
        };
      };
    })
  ]);
}
