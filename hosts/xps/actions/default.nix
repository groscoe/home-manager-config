{ config, lib, pkgs, ... }:
let
  profile = config.home.profileDirectory;
  rofi = "${config.programs.rofi.finalPackage}/bin/rofi";
  notify = "${pkgs.libnotify}/bin/notify-send";
  audioSettings = pkgs.writeText "xps-audio.json" (builtins.toJSON {
    inherit rofi notify;
    pactl = "${pkgs.pulseaudio}/bin/pactl";
    paplay = "${pkgs.pulseaudio}/bin/paplay";
    mixer = "${pkgs.pavucontrol}/bin/pavucontrol";
    bluetooth = "${profile}/bin/rofi-bluetooth";
  });
  audio = pkgs.writeShellScriptBin "xps-audio" ''
    export LC_ALL=C.UTF-8
    exec ${pkgs.python3}/bin/python3 -I ${./audio.py} --config ${audioSettings} "$@"
  '';
  entry = label: argv: { inherit label argv; };
  report = label: argv: { inherit label argv; terminal = true; };
  paletteSettings = pkgs.writeText "xps-actions.json" (builtins.toJSON {
    inherit rofi notify;
    terminal = "${profile}/bin/alacritty";
    entries = [
      (entry "Sound · Audio controls — volume, output, microphone, profiles" [ "${audio}/bin/xps-audio" "menu" ])
      (entry "Sound · Choose playback output — speakers / headphones" [ "${audio}/bin/xps-audio" "output" ])
      (entry "Sound · Choose microphone input" [ "${audio}/bin/xps-audio" "input" ])
      (entry "Sound · Bluetooth music / headset profile" [ "${audio}/bin/xps-audio" "profiles" ])
      (entry "Sound · Toggle mute on all microphones" [ "${audio}/bin/xps-audio" "mic-mute" ])
      (entry "Sound · Full application mixer" [ "${audio}/bin/xps-audio" "mixer" ])
      (entry "Connections · Wi-Fi networks" [ "${profile}/bin/rofi-wifi" ])
      (entry "Connections · Bluetooth — pair / connect headphones" [ "${profile}/bin/rofi-bluetooth" ])
      (entry "Connections · KDE Connect devices — send file / clipboard / ring" [ "${profile}/bin/rofi-kdeconnect" ])
      (report "Connections · Both Tailscale services — status" [ "/usr/bin/systemctl" "status" "liqwid-tailscale-global.service" "liqwid-tailscale-local.service" "--no-pager" ])
      (entry "Privacy · Camera access history and block controls" [ "${profile}/bin/camera-monitor" "menu" ])
      (entry "Desktop · Keyboard shortcut reference — i3 / tmux / copy mode" [ "${profile}/bin/xps-shortcuts" ])
      (entry "Desktop · Search focused application's commands" [ "${profile}/bin/xps-command-search" ])
      (entry "Desktop · Applications and windows launcher" [ rofi "-show" "combi" ])
      (entry "Desktop · Interactive screenshot" [ "/usr/bin/gnome-screenshot" "--interactive" ])
      (entry "Desktop · Notification history" [ "${config.services.dunst.package}/bin/dunstctl" "history-pop" ])
      (entry "Desktop · Pause / resume notifications — focus mode" [ "${config.services.dunst.package}/bin/dunstctl" "set-paused" "toggle" ])
      (report "System · Backup status — last success / attempt" [ "${profile}/bin/restic-backup" "--status" ])
      (report "System · Saved battery and SSD health report" [ "${profile}/bin/hardware-health" "--status" ])
      (report "System · Audio service log" [ "/usr/bin/journalctl" "--user" "-u" "xps-audio.service" "-n" "60" "--no-pager" ])
      (entry "Session · Lock / suspend / log out / power menu" [ "${profile}/bin/xps-session-menu" ])
    ];
  });
  palette = pkgs.writeShellScriptBin "xps-actions" ''
    exec ${pkgs.python3}/bin/python3 -I ${./palette.py} --config ${paletteSettings} "$@"
  '';
in {
  home.packages = [ audio palette ];
  systemd.user.services.xps-audio = {
    Unit.Description = "Audio route preferences and microphone state (PulseAudio events)";
    Service = {
      ExecStart = "${audio}/bin/xps-audio watch";
      Restart = "on-failure";
      RestartSec = 3;
      UMask = "0077";
      NoNewPrivileges = true;
    };
    Install.WantedBy = [ "default.target" ];
  };
  xdg.desktopEntries = {
    xps-audio = {
      name = "Audio controls";
      genericName = "Output, microphone, volume and Bluetooth profiles";
      exec = "${audio}/bin/xps-audio menu";
      icon = "audio-volume-high";
      categories = [ "AudioVideo" "Settings" ];
      settings.Keywords = "sound;audio;volume;headphones;microphone;mute;";
    };
    xps-actions = {
      name = "XPS actions";
      genericName = "Sound, connections, privacy, desktop and system controls";
      exec = "${palette}/bin/xps-actions";
      icon = "preferences-system";
      categories = [ "Utility" "Settings" ];
      settings.Keywords = "actions;control;settings;wifi;bluetooth;backup;camera;";
    };
  };
}
