{ lib, ... }: {
  disabledModules = [ ../clamav-scan ];
  personal.hardware = import ../hardware-profiles/qemu.nix;
  # A disposable guest must not start backups against production credentials.
  services.restic-backup.enable = lib.mkForce false;
}
