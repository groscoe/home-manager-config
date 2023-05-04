{...}:
  {
    enable = true;
    urls = [
      {
        url = "https://bbs.archlinux.org/extern.php?action=feed&tid=277462&type=atom";
        tags = ["forums"  "arch"];
        title = "Dell XPS 13 Plus 9320: Camera issues";
      }

      {
        url = "https://discourse.haskell.org/latest.rss";
        tags = ["forums" "programming" "haskell"];
        title = "Haskell discourse";
      }

      {
        url = "https://lobste.rs/rss";
        tags = ["forums" "programming"];
        title = "Lobste.rs";
      }
    ];
    autoReload = true;
    extraConfig = ''
      # unbind keys
      # unbind-key ENTER
      unbind-key j
      unbind-key k
      unbind-key J
      unbind-key K

      # bind keys - vim style
      bind-key j down
      bind-key k up
      bind-key l open
      bind-key h quit
    '';
  }
