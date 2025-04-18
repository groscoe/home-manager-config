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
          sha256 = "sha256-4+k5rSoxkTtYFh/lEjhRkVYa2S4KEzJ/IJbyJl+rJjQ=";
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
      set -x LANG en_US.UTF-8
      set -x LC_ALL en_US.UTF-8

      set -x PATH \
        $HOME/.nix-profile/bin \
      	$HOME/.cargo/bin \
      	$HOME/.npm-packages/bin \
      	$HOME/.local/bin \
      	$HOME/.cabal/bin \
      	$PATH

      set -x EDITOR vim

      # Nix
      if [ -e $HOME/.nix-profile/etc/profile.d/nix.sh ]
        fenv source $HOME/.nix-profile/etc/profile.d/nix.sh
      elif [ -e /etc/profile.d/nix.sh ]
        fenv source /etc/profile.d/nix.sh
      else
        set -x PATH \
          /nix/var/nix/profiles/default/bin \
          $PATH
      end
      set -x LOCALE_ARCHIVE /usr/lib/locale/locale-archive
      source (direnv hook fish | psub)

      # Homebrew
      if [ -e /opt/homebrew/bin/brew ]
        eval "$(/opt/homebrew/bin/brew shellenv)"

        # >>> conda initialize >>>
        # !! Contents within this block are managed by 'conda init' !!
        if test -f /opt/homebrew/Caskroom/miniconda/base/bin/conda
            eval /opt/homebrew/Caskroom/miniconda/base/bin/conda "shell.fish" "hook" $argv | source
        else
            if test -f "/opt/homebrew/Caskroom/miniconda/base/etc/fish/conf.d/conda.fish"
                . "/opt/homebrew/Caskroom/miniconda/base/etc/fish/conf.d/conda.fish"
            else
                set -x PATH "/opt/homebrew/Caskroom/miniconda/base/bin" $PATH
            end
        end
        # <<< conda initialize <<<
      end

      # Avoid opening a popup for GPG
      if [ -e /usr/bin/gpg ]
        set -x GPG_TTY (tty)
      end

      # Auto start the SSH agent ont linux
      if test (uname) = "Linux"
          if not set -q SSH_AUTH_SOCK
              eval (ssh-agent -c) > /dev/null
          end
      end
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

      fish_user_key_bindings = ''
        # Defined in /usr/share/fish/vendor_functions.d/fzf_key_bindings.fish @ line 16
        function fzf_key_bindings

          # Store current token in $dir as root for the 'find' command
          function fzf-file-widget -d "List files and folders"
            set -l commandline (__fzf_parse_commandline)
            set -l dir $commandline[1]
            set -l fzf_query $commandline[2]
            set -l prefix $commandline[3]

            # "-path \$dir'*/\\.*'" matches hidden files/folders inside $dir but not
            # $dir itself, even if hidden.
            test -n "$FZF_CTRL_T_COMMAND"; or set -l FZF_CTRL_T_COMMAND "
            command find -L \$dir -mindepth 1 \\( -path \$dir'*/\\.*' -o -fstype 'sysfs' -o -fstype 'devfs' -o -fstype 'devtmpfs' \\) -prune \
            -o -type f -print \
            -o -type d -print \
            -o -type l -print 2> /dev/null | sed 's@^\./@@'"

            test -n "$FZF_TMUX_HEIGHT"; or set FZF_TMUX_HEIGHT 40%
            begin
              set -lx FZF_DEFAULT_OPTS "--height $FZF_TMUX_HEIGHT --reverse --bind=ctrl-z:ignore $FZF_DEFAULT_OPTS $FZF_CTRL_T_OPTS"
              eval "$FZF_CTRL_T_COMMAND | "(__fzfcmd)' -m --query "'$fzf_query'"' | while read -l r; set result $result $r; end
            end
            if [ -z "$result" ]
              commandline -f repaint
              return
            else
              # Remove last token from commandline.
              commandline -t ""
            end
            for i in $result
              commandline -it -- $prefix
              commandline -it -- (string escape $i)
              commandline -it -- ' '
            end
            commandline -f repaint
          end

          function fzf-cd-widget -d "Change directory"
            set -l commandline (__fzf_parse_commandline)
            set -l dir $commandline[1]
            set -l fzf_query $commandline[2]
            set -l prefix $commandline[3]

            test -n "$FZF_ALT_C_COMMAND"; or set -l FZF_ALT_C_COMMAND "
            command find -L \$dir -mindepth 1 \\( -path \$dir'*/\\.*' -o -fstype 'sysfs' -o -fstype 'devfs' -o -fstype 'devtmpfs' \\) -prune \
            -o -type d -print 2> /dev/null | sed 's@^\./@@'"
            test -n "$FZF_TMUX_HEIGHT"; or set FZF_TMUX_HEIGHT 40%
            begin
              set -lx FZF_DEFAULT_OPTS "--height $FZF_TMUX_HEIGHT --reverse --bind=ctrl-z:ignore $FZF_DEFAULT_OPTS $FZF_ALT_C_OPTS"
              eval "$FZF_ALT_C_COMMAND | "(__fzfcmd)' +m --query "'$fzf_query'"' | read -l result

              if [ -n "$result" ]
                cd -- $result

                # Remove last token from commandline.
                commandline -t ""
                commandline -it -- $prefix
              end
            end

            commandline -f repaint
          end

          function __fzfcmd
            test -n "$FZF_TMUX"; or set FZF_TMUX 0
            test -n "$FZF_TMUX_HEIGHT"; or set FZF_TMUX_HEIGHT 40%
            if [ -n "$FZF_TMUX_OPTS" ]
              echo "fzf-tmux $FZF_TMUX_OPTS -- "
            else if [ $FZF_TMUX -eq 1 ]
              echo "fzf-tmux -d$FZF_TMUX_HEIGHT -- "
            else
              echo "fzf"
            end
          end

          bind \ct fzf-file-widget
          bind \ec fzf-cd-widget

          if bind -M insert > /dev/null 2>&1
            bind -M insert \ct fzf-file-widget
            bind -M insert \cr fzf-history-widget
            bind -M insert \ec fzf-cd-widget
          end

          function __fzf_parse_commandline -d 'Parse the current command line token and return split of existing filepath, fzf query, and optional -option= prefix'
            set -l commandline (commandline -t)

            # strip -option= from token if present
            set -l prefix (string match -r -- '^-[^\s=]+=' $commandline)
            set commandline (string replace -- "$prefix" "" $commandline)

            # eval is used to do shell expansion on paths
            eval set commandline $commandline

            if [ -z $commandline ]
              # Default to current directory with no --query
              set dir '.'
              set fzf_query ""
            else
              set dir (__fzf_get_dir $commandline)

              if [ "$dir" = "." -a (string sub -l 1 -- $commandline) != '.' ]
                # if $dir is "." but commandline is not a relative path, this means no file path found
                set fzf_query $commandline
              else
                # Also remove trailing slash after dir, to "split" input properly
                set fzf_query (string replace -r "^$dir/?" -- "" "$commandline")
              end
            end

            echo $dir
            echo $fzf_query
            echo $prefix
          end

          function __fzf_get_dir -d 'Find the longest existing filepath from input string'
            set dir $argv

            # Strip all trailing slashes. Ignore if $dir is root dir (/)
            if [ (string length -- $dir) -gt 1 ]
              set dir (string replace -r '/*$' -- "" $dir)
            end

            # Iteratively check if dir exists and strip tail end of path
            while [ ! -d "$dir" ]
              # If path is absolute, this can keep going until ends up at /
              # If path is relative, this can keep going until entire input is consumed, dirname returns "."
              set dir (dirname -- "$dir")
            end

            echo $dir
          end

        end

        fzf_key_bindings
      '';

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
