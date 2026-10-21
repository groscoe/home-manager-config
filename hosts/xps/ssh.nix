{ config, ... }: {
  programs.ssh.matchBlocks = {
    github = {
      hostname = "github.com";
      user = "git";
      identityFile = [ "${config.home.homeDirectory}/.ssh/id_rsa" ];
    };
    "*".addKeysToAgent = "yes";
  };
}
