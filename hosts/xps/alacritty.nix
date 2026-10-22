{ config, pkgs, ... }:
let
  wrapped = config.lib.nixGL.wrap pkgs.alacritty;
  childEnv = pkgs.writeScript "alacritty-child-env" (
    "#!${pkgs.python3}/bin/python3\n" + builtins.readFile ./alacritty-child-env.py
  );
  launcher = pkgs.writeScript "alacritty-launcher" (
    "#!${pkgs.python3}/bin/python3\n" + builtins.replaceStrings
      [ "@wrappedAlacritty@" "@cleanChild@" "@fish@" ]
      [ "${wrapped}/bin/alacritty" "${childEnv}" "${config.programs.fish.package}/bin/fish" ]
      (builtins.readFile ./alacritty-launcher.py)
  );
  terminal = pkgs.symlinkJoin {
    name = "alacritty-${pkgs.alacritty.version}";
    inherit (pkgs.alacritty) meta version;
    paths = [ wrapped ];
    postBuild = ''
      rm "$out/bin/alacritty"
      ln -s ${launcher} "$out/bin/alacritty"
    '';
  };
in {
  home.packages = [ terminal ];
}
