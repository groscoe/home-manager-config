{ config, ... }:
{
  enable = true;
  dotDir = "${config.xdg.configHome}/zsh";

  initExtra = ''
    export LANG=en_US.UTF-8
    export LC_ALL=en_US.UTF-8

    hm_user="$(id -un)"
    export PATH="/etc/profiles/per-user/$hm_user/bin:/run/current-system/sw/bin:$HOME/.nix-profile/bin:$HOME/.cargo/bin:$HOME/.npm-packages/bin:$HOME/.local/bin:$HOME/.cabal/bin:$PATH"

    if command -v nvim >/dev/null 2>&1; then
      export EDITOR=nvim
    else
      export EDITOR=vim
    fi

    # Nix
    if [ -e "$HOME/.nix-profile/etc/profile.d/nix.sh" ]; then
      . "$HOME/.nix-profile/etc/profile.d/nix.sh"
    elif [ -e /etc/profile.d/nix.sh ]; then
      . /etc/profile.d/nix.sh
    else
      export PATH="/nix/var/nix/profiles/default/bin:$PATH"
    fi

    if [ "$(uname)" = "Linux" ]; then
      export LOCALE_ARCHIVE=/usr/lib/locale/locale-archive
    fi

    if command -v direnv >/dev/null 2>&1; then
      eval "$(direnv hook zsh)"
    fi

    # Homebrew
    if [ -e /opt/homebrew/bin/brew ]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"

      if [ -d /opt/homebrew/share/google-cloud-sdk/bin ]; then
        export PATH="/opt/homebrew/share/google-cloud-sdk/bin:$PATH"
      fi

      # >>> conda initialize >>>
      # !! Contents within this block are managed by 'conda init' !!
      if [ -f /opt/homebrew/Caskroom/miniconda/base/bin/conda ]; then
        eval "$(/opt/homebrew/Caskroom/miniconda/base/bin/conda shell.zsh hook)"
      elif [ -f /opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh ]; then
        . /opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh
      else
        export PATH="/opt/homebrew/Caskroom/miniconda/base/bin:$PATH"
      fi
      # <<< conda initialize <<<
    fi

    # Avoid opening a popup for GPG
    if command -v gpg >/dev/null 2>&1; then
      export GPG_TTY="$(tty)"
    fi

    # FZF integration (aligned with fish defaults)
    export RIPGREP_CONFIG_PATH="$HOME/.ripgreprc"
    export FZF_FIND_FILE_OPTS="--layout=reverse --bind='ctrl-t:toggle-preview' --preview='$HOME/Projects/preview.sh {}' --height=100%"
    export FZF_FIND_FILE_COMMAND="fd -L -H"

    # Reuse existing aliases/functions with minimal churn.
    if [ -f "$HOME/.bash_aliases" ]; then
      source "$HOME/.bash_aliases"
    fi

    if command -v atuin >/dev/null 2>&1; then
      eval "$(atuin init zsh)"
    fi

    # Keep Ctrl-R bound to Atuin search.
    if command -v atuin >/dev/null 2>&1 && zle -la | grep -qx "atuin-search"; then
      bindkey '^R' atuin-search
      bindkey -M viins '^R' atuin-search-viins
    fi
  '';
}
