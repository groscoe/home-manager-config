# Disposable xps recovery rehearsal

Read [RECOVERY.md](../../RECOVERY.md) for recovery of an actual machine and the
measured results. This directory controls only a private synthetic Ubuntu guest.
It does not install or activate a profile on the physical xps.

## Requirements and limits

- Linux x86_64 with usable `/dev/kvm`, at least 8 GiB RAM available for the guest,
  and at least 80 GiB free on the filesystem holding the test cache.
- Existing multi-user Nix with flakes; Ubuntu's `gpgv`, cloud-image public
  keyring at `/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg`, OpenSSH client,
  `openssl` and a clean canonical source checkout.
- Downloads from the pinned Nix inputs, upstream Nix release and the dated
  Ubuntu image. The 2026-10-20 cloud image is intentionally reproducible, not
  a rolling latest URL. An unavailable image requires a reviewed replacement.

The flake app pins QEMU, OVMF, cloud-utils and Python through the existing
lock file. Its paths are immutable runtime metadata; it does not add them to
the user profile. The test directory is fixed to
`/home/groscoe/.cache/hm-restore-test`, deliberately excluded from real backups.
The runner records its filesystem identity and refuses symlinks, nonprivate
directories, an unmarked nonempty directory, external disk paths and root
execution. It uses only user-owned regular disk files, never block-device or
host-directory passthrough. The watcher pauses the guest below 24 GiB host free
space; `start` requires 32 GiB. Virtual disks are sparse, not reserved space.

The VM has 4 vCPU, 8 GiB RAM, a Virtio GPU and private UEFI variables. Its root,
Nix and vault virtual disks have maximum sizes 24, 96 and 8 GiB. It uses private
Unix sockets for QMP/VNC and a single SSH forward on **127.0.0.1:22222**. Guest
keys and login credentials are newly generated; SSH never inherits an agent,
user alias configuration or unpinned host key. Every guest stage checks the
generated UUID, root marker, QEMU/KVM virtualization and test hostname first.
The guest bootstrap also verifies Ubuntu 22.04 and x86_64 before writing its
synthetic volumes. Its passwordless sudo account is test-only.

Normal user-mode networking permits outbound access, including to the LAN.
Never sign in to real services or add private credentials to this guest. For
offline acceptance restart with `start --isolated`; QEMU `restrict=on` blocks
outbound access while retaining the explicit loopback SSH forward.

## Run

From the clean canonical checkout on xps:

```sh
nix run .#xps-restore-test -- prepare
nix run .#xps-restore-test -- start
nix run .#xps-restore-test -- exercise bootstrap
nix run .#xps-restore-test -- exercise fixtures
nix run .#xps-restore-test -- exercise policies
nix run .#xps-restore-test -- exercise build
nix run .#xps-restore-test -- exercise activate
nix run .#xps-restore-test -- exercise applications
nix run .#xps-restore-test -- exercise backup
nix run .#xps-restore-test -- exercise desktop
nix run .#xps-restore-test -- exercise rollback
nix run .#xps-restore-test -- powerdown
```

`prepare --repo /absolute/path/to/clean/checkout` selects the source explicitly;
it defaults to `/home/groscoe/Projects/home-manager-config`. It records HEAD and
transfers only a Git bundle. Dirty source is refused. A successful build does
not imply source-authenticity verification: review/trust the commit before
running; the guest does not borrow the user's trusted GPG keyring.

Bootstrap and cold builds take minutes and can compile pinned overrides.
Per-stage logs/exit codes/durations live in `runs/INSTANCE/evidence`; retries
retain the earlier failure. `status` performs an identity-checked query, not an
overall acceptance verdict. `applications` executes the synthetic notebook and
C compiler tests. `backup` installs Docker **inside the guest**, uses a stopped
dummy container and local disposable Restic repository, and checks ownership,
contents and running-database refusal. It never touches production backups.

`desktop` installs the supplied SDDM session bridge, logs in with the generated
guest credential and uses a test-only Polybar monitor override. There is no
fingerprint device, physical Intel acceleration/backlight, Wi-Fi, real stereo
device or private tailnet. Those need physical acceptance. Missing wallpaper
and hardware modules remain explicit limitations. The optional Qt theme test
uses synthetic UI conversations. No production password is needed in the VM.

After guest shutdown has completed (the private `qmp.sock` disappears):

```sh
nix run .#xps-restore-test -- start --isolated
nix run .#xps-restore-test -- exercise reboot-check
nix run .#xps-restore-test -- powerdown
```

This does not log in graphically after reboot; the reboot check covers mounts,
daemon availability/build and policy. Use `desktop` again for graphical login.
Never run two instances simultaneously: they deliberately share one loopback
SSH port. `prepare` creates a new instance and advances `current-run`; first
stop the old instance and retain its evidence. The verified read-only base is
reused, but no previous guest store/home is shared with the new guest.

## Credentials, evidence and cleanup

`runs/INSTANCE/guest-login.txt`, cloud-init seed/user-data and SSH keys are
private test material. Do not commit them, raw disks or unreviewed private logs.
Keep source/lock/image digests, non-secret result summaries and package versions
with the recovery guide. `hm-i3-session` and `hm-i3.desktop` are also the explicit
OS session bridge used by the recovery instructions; installing them is a
deliberate root step, not an automatic Home Manager activation.

There is intentionally no broad deletion command. Shut down the recorded guest,
verify no QEMU process uses its exact disk paths, retain evidence and remove
only that instance directory's disposable disk/seed/key files. Leave the shared
verified base while another overlay references it. Never delete a mountpoint,
external drive or unrelated cache to make room. Exiting an SSH shell does not
stop a daemonized guest; use the recorded controller's `powerdown`.

The lightweight flake check `checks.x86_64-linux.restore-vm` tests runner
boundaries without booting a guest, accessing KVM or downloading an OS. The
full VM run is explicit and is not part of ordinary `nix flake check`.
