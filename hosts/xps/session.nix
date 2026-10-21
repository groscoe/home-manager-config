{ pkgs, ... }:
let
  xSettings = pkgs.writeShellApplication {
    name = "xps-x-settings";
    runtimeInputs = [
      pkgs.xorg.setxkbmap
      pkgs.xorg.xmodmap
      pkgs.xf86_input_wacom
      pkgs.gnused
    ];
    text = builtins.readFile ./x-settings.sh;
  };
in {
  home.packages = [ xSettings ];
  home.file.".config/i3/config".source = pkgs.replaceVars ../../i3/config/i3/config {
    xpsXSettings = "${xSettings}/bin/xps-x-settings";
  };
  xdg.configFile."fish/conf.d/90-persistent-ssh-agent.fish".source =
    ./90-persistent-ssh-agent.fish;
}
