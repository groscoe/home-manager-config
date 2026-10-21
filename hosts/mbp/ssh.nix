{ config, ... }: {
  programs.ssh.matchBlocks = {
    "192.168.1.2" = {
      hostname = "192.168.1.2";
      port = 2222;
      user = config.home.username;
      forwardAgent = true;
    };
    xps = {
      hostname = "xps";
      port = 2222;
      user = config.home.username;
      forwardAgent = true;
    };
    "*" = {
      addKeysToAgent = "yes";
      identityFile = [ "~/.ssh/id_ed25519" ];
      extraOptions.UseKeychain = "yes";
    };
  };
}
