# Common variables
set -x PATH \
  $HOME/.cargo/bin \
  $HOME/.npm-packages/bin \
  $HOME/.local/bin \
  $HOME/.cabal/bin \
  $PATH

set -x EDITOR vim

# My custom, decade-old, function definitions
bass source ~/.bash_aliases

# Nix
bass source $HOME/.nix-profile/etc/profile.d/nix.sh
set -x LOCALE_ARCHIVE /usr/lib/locale/locale-archive
source (direnv hook fish | psub)

# FZF integration
set -x RIPGREP_CONFIG_PATH $HOME/.ripgreprc
set -x FZF_FIND_FILE_OPTS "--layout=reverse --bind='ctrl-t:toggle-preview' --preview='/home/groscoe/Projects/preview.sh {}' --height=100%"
set -x FZF_FIND_FILE_COMMAND "fd -L -H"

# Custom functions
. $HOME/.config/fish/functions/rprompt.fish

# Dynamic color scheme
if test -f $HOME/.cache/wal/sequences
  /usr/bin/cat $HOME/.cache/wal/sequences
end
