{ config, lib, pkgs, ... }:
let
  hw = config.personal.hardware;
  xSettings = pkgs.writeShellApplication {
    name = "xps-x-settings";
    runtimeInputs = [
      pkgs.xorg.setxkbmap
      pkgs.xorg.xmodmap
      pkgs.xf86_input_wacom
      pkgs.gnused
    ];
    text = lib.replaceStrings
      [ "@keyboardLayout@" "@keyboardOptions@" "@keyboardRemaps@" "@tablet@" ]
      [
        (lib.escapeShellArg hw.keyboardLayout)
        (lib.escapeShellArgs (lib.concatMap (option: [ "-option" option ]) hw.keyboardOptions))
        (lib.concatMapStringsSep "\n" (mapping: "xmodmap -e " + lib.escapeShellArg mapping) hw.keyboardRemaps)
        (lib.optionalString (hw.tablet != null) ''
          while IFS= read -r stylus_id; do
            xsetwacom set "$stylus_id" rotate ${lib.escapeShellArg hw.tablet.rotation}
            xsetwacom set "$stylus_id" area ${lib.escapeShellArgs (map toString hw.tablet.area)}
          done < <(xsetwacom list devices | sed -nE 's/.*id: ([0-9]+).*STYLUS.*/\1/p')
        '')
      ]
      (builtins.readFile ./x-settings.sh);
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
