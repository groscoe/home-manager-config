# Common variables
set -x PATH \
  /home/groscoe/.cargo/bin \
  /home/groscoe/.npm-packages/bin \
  /home/groscoe/.local/bin \
  /home/groscoe/.cabal/bin \
  $PATH

set -x EDITOR vim

# My custom, decade-old, function definitions
bass source ~/.bash_aliases

# Nix
bass source /home/groscoe/.nix-profile/etc/profile.d/nix.sh
set -x LOCALE_ARCHIVE /usr/lib/locale/locale-archive

# FZF integration
set -x RIPGREP_CONFIG_PATH $HOME/.ripgreprc
set -x FZF_FIND_FILE_OPTS "--layout=reverse --bind='ctrl-t:toggle-preview' --preview='/home/groscoe/Projects/preview.sh {}' --height=100%"
set -x FZF_FIND_FILE_COMMAND "fd -L -H"

# Custom functions
. ~/.config/fish/functions/rprompt.fish
