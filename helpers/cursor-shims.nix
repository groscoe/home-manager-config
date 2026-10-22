{ pkgs, ... }:
let
  agent = pkgs.writeShellScript "agent" ''
    exec "$HOME/.local/bin/cursor-agent" "$@"
  '';
  cursor = pkgs.writeShellScript "cursor" ''
    # Prefer an installed IDE. Skip every symlink to this shim to avoid recursion.
    oldIFS="$IFS"
    IFS=:
    for directory in $PATH; do
      [ -n "$directory" ] || continue
      candidate="$directory/cursor"
      if [ -x "$candidate" ] && ! [ "$candidate" -ef "$0" ]; then
        IFS="$oldIFS"
        exec "$candidate" "$@"
      fi
    done
    IFS="$oldIFS"
    if [ "''${1:-}" != agent ]; then
      printf '%s\n' "No Cursor IDE found. Use 'cursor agent' or 'agent' for the installed agent." >&2
      exit 1
    fi
    exec "$HOME/.local/bin/cursor-agent" "$@"
  '';
in {
  # The xps application module supplies the agent binary; login state stays local.
  home.file.".local/bin/agent".source = agent;
  home.file.".local/bin/cursor".source = cursor;
}
