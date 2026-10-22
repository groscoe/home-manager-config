{ config, pkgs, ... }:
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
  imports = [ ../../helpers/cursor-shims.nix ];
  home.packages = [ xSettings ];
  home.file.".xprofile".text = ''
    # HiDPI is applied centrally by .xsessionrc. Reuse the persistent agent.
    if [ -z "''${SSH_AUTH_SOCK:-}" ] || [ ! -S "$SSH_AUTH_SOCK" ]; then
      if [ -n "''${XDG_RUNTIME_DIR:-}" ] && [ -S "$XDG_RUNTIME_DIR/ssh-agent" ]; then
        export SSH_AUTH_SOCK="$XDG_RUNTIME_DIR/ssh-agent"
      fi
    fi
  '';
  home.file.".config/i3/config".source = pkgs.replaceVars ../../i3/config/i3/config {
    xpsPolybar = "${config.home.profileDirectory}/bin/xps-start-polybar";
    xpsPicom = "${config.home.profileDirectory}/bin/xps-start-picom";
    xpsXSettings = "${xSettings}/bin/xps-x-settings";
  };
  xdg.configFile."fish/conf.d/90-persistent-ssh-agent.fish".source =
    ./90-persistent-ssh-agent.fish;
}
