{ lib, runCommand, python3, restic, bash, coreutils }:
let
  source = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ./run-tests.py
      ../restic-backup
      ../hardware-health
      ../xps-desktop
      ../hosts/xps/alacritty-launcher.py
      ../hosts/xps/alacritty-child-env.py
      ../hosts/xps/theme/shortcuts.py
      ../hosts/xps/command-search/search.py
      ../hosts/xps/tests
    ];
  };
in
runCommand "personal-config-tests" {
  nativeBuildInputs = [ python3 restic bash ];
  # VNC port-collision tests bind loopback sockets, without external connections.
  __darwinAllowLocalNetworking = true;
} ''
  export HOME="$TMPDIR/home"
  export XDG_CONFIG_HOME="$HOME/.config"
  export XDG_CACHE_HOME="$HOME/.cache"
  export XDG_STATE_HOME="$HOME/.local/state"
  export XDG_DATA_HOME="$HOME/.local/share"
  mkdir -p "$HOME"
  export PYTHONDONTWRITEBYTECODE=1
  cp -R ${source} source
  chmod -R u+w source
  # The live Ubuntu/macOS loader uses the OS env utility. Linux build sandboxes
  # have no /usr/bin/env; use the pinned equivalent only in this fixture copy.
  substituteInPlace source/restic-backup/runner.py \
    --replace-fail 'exec /usr/bin/env -0' 'exec ${coreutils}/bin/env -0'
  ${python3}/bin/python3 -I source/validation/run-tests.py --report "$out"
''
