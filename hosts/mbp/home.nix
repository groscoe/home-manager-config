{ config, pkgs, ... }: {
  imports = [ ./ssh.nix ];
  assertions = [{
    assertion = pkgs.stdenv.hostPlatform.system == "aarch64-darwin";
    message = "The mbp profile requires aarch64-darwin.";
  }];
  home.homeDirectory = "/Users/${config.home.username}";

  # Preserve the Mac's current Atuin setting and package selection.
  programs.atuin.settings.secrets_filter = "false";

  services.hardware-health = {
    enable = true;
    devices = [ "/dev/disk0" ];
    remoteReports = [ {
      name = "xps";
      host = "groscoe@192.168.1.2";
      port = 2222;
      command = "/home/groscoe/.local/bin/hardware-health";
    } ];
  };

  services.restic-backup = {
    enable = true;
    paths = [ config.home.homeDirectory ];
  };
  services.xps-desktop = {
    enable = true;
    sshHost = "192.168.1.2";
    sshPort = 2222;
    remoteUid = 1000;
    remoteHome = "/home/groscoe";
    localPort = 59320;
  };
}
