{pkgs, ...}:
  {
    enable = true;

    plugins = [
      {
        name = "foreign-env";
        src = pkgs.fetchFromGitHub {
          owner = "oh-my-fish";
          repo = "plugin-foreign-env";
          rev = "master";
          sha256 = "sha256-3h03WQrBZmTXZLkQh1oVyhv6zlyYsSDS7HTHr+7WjY8=";
        };
      }

      {
        name = "bass";
        src = pkgs.fetchFromGitHub {
          owner = "edc";
          repo = "bass";
          rev = "master";
          sha256 = "sha256-fl4/Pgtkojk5AE52wpGDnuLajQxHoVqyphE90IIPYFU=";
        };
      }
    ];

    shellInit = ''
      # Common variables
      set -x PATH \
      	$HOME/.cargo/bin \
      	$HOME/.npm-packages/bin \
      	$HOME/.local/bin \
      	$HOME/.cabal/bin \
      	$PATH

      set -x EDITOR vim

      # Nix
      fenv source $HOME/.nix-profile/etc/profile.d/nix.sh
      set -x LOCALE_ARCHIVE /usr/lib/locale/locale-archive
      source (direnv hook fish | psub)
    '';

    interactiveShellInit = ''
      # My custom, decade-old, function definitions
      bass source ~/.bash_aliases

      # FZF integration
      set -x RIPGREP_CONFIG_PATH $HOME/.ripgreprc
      set -x FZF_FIND_FILE_OPTS "--layout=reverse --bind='ctrl-t:toggle-preview' --preview='/home/groscoe/Projects/preview.sh {}' --height=100%"
      set -x FZF_FIND_FILE_COMMAND "fd -L -H"
    '';

    functions = {
      fish_right_prompt = ''
        if test $CMD_DURATION
            # Show duration of the last command in seconds
            set duration (echo "$CMD_DURATION 1000" | awk '{printf "%.3fs", $1 / $2}')
            echo $duration
        end
      '';

      fish_user_key_bindings = "fzf_key_bindings";

      wrap-notify = ''
        # Execute the command and its arguments
        $argv

        # Send a notification
        notify-send "finished"
      '';

      wrap-notify-pgrep = ''
        # Wait for the argument to be finished
        pwait -f $args

        notify-send "finished"
      '';
    };
  }
