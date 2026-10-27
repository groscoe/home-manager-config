# Recovering xps from the canonical configuration

This guide restores the declared xps configuration onto Ubuntu and explains the
private state and OS setup that must be recovered separately. It is not a disk
image, an Ubuntu release-upgrade procedure, or an encryption-conversion recipe.

Rehearsed on 2026-10-24 using a fresh Ubuntu 22.04 virtual machine, separate
synthetic `/nix` and `/vault` filesystems and no production credentials or shared
host Nix store. The results and explicit limits are in section 15. Follow the
steps in order; building the profile does not restore the private state.

All shell examples in this guide use **Bash**, including variable assignments
and environment-file loading. Start `/bin/bash` when following them from Fish.

## 1. What the repository recreates

One repository serves both machines:

| Machine | User configuration | Additional system layer |
| --- | --- | --- |
| xps | `homeConfigurations.xps`, Ubuntu `x86_64-linux` | Selected policies through `xps-host` |
| mbp | `homeConfigurations.mbp`, `aarch64-darwin` | `darwinConfigurations.mbp`, including the existing Homebrew policy |

The xps profile declares the desktop, terminal, compositor, bar, Rofi menus,
notifications, shell and SSH client settings, tmux behavior, user applications,
Python/Jupyter environments, development shells, personal helpers and user timers.
The Ubuntu companion declares SSH X11 forwarding, journal retention, the reviewed
PAM/SDDM fingerprint/password policies, Sugar Candy and Nix startup units.

Home Manager does not install Ubuntu, partition disks, restore data or secrets,
install hardware drivers, choose the OS login shell/display manager, reproduce
the entire SSH server/firewall/Docker setup, or join either Tailscale network.
Matching CPU architecture alone does not prove compatibility with a different
GPU, fingerprint reader or backlight device. The companion currently refuses
systems other than Ubuntu 22.04 on x86_64.

Keep `home.stateVersion = "22.05"`. It records Home Manager's compatibility
baseline; it is not a package-version selector to raise during recovery.

## 2. Before replacing the old installation

Do these while the old machine still works:

1. Verify the canonical repository is clean and its intended commit is pushed.
   Restic excludes `.git` histories; a source-file backup does not replace
   publishing commits or exporting unpublished Git history.
2. Run `restic-backup --status`, complete a guarded `restic-backup --run`, and
   restore representative files to a separate staging directory. Keep the
   repository password and storage credentials independently of both laptops.
3. Verify the selected protected exports are current and included in that
   snapshot. A failed export must be resolved before calling the backup complete.
4. Preserve the remaining OS configuration and hardware inventory separately.
   Home plus `/vault` backups do not automatically cover `/etc` or `/var`.
5. Record the actual mount/encryption layout and how to unlock it. A synthetic
   VM's filesystem labels and device names must never be copied to real disks.

Useful read-only inventory commands, from Bash:

```sh
cd /home/groscoe/Projects/home-manager-config
git status --short
git log -1 --show-signature
git ls-remote origin refs/heads/main
sha256sum flake.lock
lsblk -f
findmnt --real
uname -r
dpkg-query -W -f='${binary:Package}\t${Version}\t${db:Status-Status}\n' > ubuntu-packages.tsv
getent passwd groscoe
id groscoe
timedatectl
```

Treat the following as private recovery material, outside Git and the Nix store:

| Material | Recovery requirement |
| --- | --- |
| SSH private keys, authorized clients, known-host history and `/etc/ssh/ssh_host_*` | Restore privately; retain all four approved client keys; verify a deliberately regenerated server fingerprint through a trusted route |
| GPG private keys and trust data | Restore securely or import from the independent recovery copy; commits require signing |
| Restic environment/password and backend credentials | Restore from independent storage; never print their values or put them in Nix expressions |
| Both Tailscale identities | Restore before starting the corresponding daemons, or deliberately re-enroll as new devices |
| Application data | Browser profiles, notebooks, photos/music, torrents, Dropbox and KDE Connect state need their backups |
| Protected archives | Work Tailscale state, the Desktop LUKS-header backup and stopped Onebus PostGIS files have separate export archives |
| OS settings | Preserve reviewed `/etc/ssh`, `/etc/nix`, `/etc/ufw`, APT sources/keyrings, systemd/udev customizations, mount and encryption records |
| Docker and databases outside the selected roots | Inventory and back up explicitly; a file backup is not automatically a consistent live-database backup |

The existing xps uses IPU6 camera packages, `libcamhal`/Intel imaging libraries,
OEM metadata and Ubuntu's fingerprint packages. Save their inventory and signed
repository configuration before reinstalling. The VM does not validate these
drivers. Reinstall the appropriate supported drivers for the actual hardware;
do not install every old OEM package blindly on a replacement computer.

## 3. Establish the new Ubuntu host

The rehearsal target is Ubuntu **22.04 amd64**, a sudo-capable `groscoe` account
with home `/home/groscoe`, UID 1000 and a private primary group `groscoe`.
Use a normal password-protected administrator account. The test VM's throwaway
keys, password and passwordless-sudo rule are test controls, not production
account settings to reproduce.

Use Ubuntu's installer and an independently reviewed storage plan to establish
the OS, hardware support, `/home`, `/nix` and `/vault`. Mount and unlock the real
volumes before installing or starting software that depends on them. Verify:

```sh
cat /etc/os-release
uname -m
id
findmnt /nix
findmnt /vault
```

The following ordinary Ubuntu packages were supplied to the fresh guest. They
provide the native tools, X11/SDDM/PAM libraries and services expected by the
declared configuration. Ubuntu package versions remain security-updateable;
the rehearsal records the versions actually used.

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends \
  ca-certificates curl git xz-utils bzip2 python3 sudo openssh-server \
  dbus-user-session dbus-x11 xorg xauth xvfb \
  python3-pyqt5 python3-pyqt5.qtquick \
  fprintd libpam-fprintd i3lock sddm \
  qml-module-qtquick-layouts qml-module-qtquick-controls2 \
  qml-module-qtgraphicaleffects libqt5svg5 \
  network-manager bluez pulseaudio policykit-1 gnome-screenshot fonts-dejavu-core
```

This list is not a complete inventory of xps's OS packages. Docker, ClamAV and
signature updating, UFW, storage/encryption tools and hardware-specific drivers
require their own reviewed host setup. The fresh cloud image also contains
packages that were not requested explicitly; retain its manifest with the
rehearsal evidence instead of treating this command as an entire OS definition.

Restore OS timezone and console-keyboard settings separately. Current xps uses
`America/Sao_Paulo`; the VM retained UTC. Home Manager's ABNT-2 X11 mapping does
not set the pre-login console or encrypted-volume unlock keyboard layout.

Choose SDDM as the display manager if the package installation asks. Keep a
working console or authenticated SSH session until login and password fallback
have been checked. Do not end the only working session to test authentication.

## 4. Install multi-user Nix reproducibly

The rehearsal uses upstream Nix **2.34.9**. Its fixed Linux installer archive was
verified against SHA256
`e8912e087582b3799e0e5a6b06f9d63386c54821f77ad4de3b9b748736ad364e`.
Selecting a different version requires verifying its own published checksum and
rerunning the compatibility/startup checks; do not update the flake inputs as
an incidental part of recovery.

Run the following in Bash as the normal administrator:

```sh
mkdir -p /home/groscoe/recovery-work
chmod 700 /home/groscoe/recovery-work
cd /home/groscoe/recovery-work
curl --fail --location --output nix-2.34.9-x86_64-linux.tar.xz \
  https://releases.nixos.org/nix/nix-2.34.9/nix-2.34.9-x86_64-linux.tar.xz
echo 'e8912e087582b3799e0e5a6b06f9d63386c54821f77ad4de3b9b748736ad364e  nix-2.34.9-x86_64-linux.tar.xz' | sha256sum -c -
tar -xJf nix-2.34.9-x86_64-linux.tar.xz
sudo -H sh ./nix-2.34.9-x86_64-linux/install \
  --daemon --yes --no-modify-profile --no-channel-add
```

`sudo -H` supplies root's actual home. The first cloud-init attempt failed
because `HOME` was absent; the corrected unattended bootstrap explicitly sets
it to `/root`. Preserve that requirement in service/cloud-init automation.

Enable flakes in `/etc/nix/nix.conf`, preserving any existing installer settings:

```text
experimental-features = nix-command flakes
```

Then restart only the new host's Nix daemon after reviewing the configuration:

```sh
sudo systemctl restart nix-daemon.service
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
nix --version
nix store info --store daemon
```

The constrained VM also sets `max-jobs = 2` and `cores = 2`. These are test
resource limits, not required production tuning. Restore deliberate Nix cache
and trust policy separately; never copy tokens or a private `netrc` into the
repository. The retired MLabs global cache entry should not be resurrected.

## 5. Obtain the canonical configuration

Restore the SSH client identity privately before using the SSH Git remote, or
transfer a verified Git bundle from a trusted machine. The rehearsal uses a
bundle so the guest needs no real Git credentials or forwarded agent.

```sh
mkdir -p /home/groscoe/Projects
git clone git@github.com:groscoe/home-manager-config.git \
  /home/groscoe/Projects/home-manager-config
cd /home/groscoe/Projects/home-manager-config
git status --short
git log -1 --show-signature
sha256sum flake.lock
```

Check out the intended reviewed revision. Verify its signature using the
independently trusted public signing key; do not equate an unknown key with a
verified identity. The rehearsal baseline is signed commit
`4c41de134709a73ae7fce0fce81f45d0a36f1580`. A test-only timeout adjustment is
recorded in the failure appendix. Keep `flake.lock`; do not run a blanket update
while trying to reproduce a known configuration.

## 6. Restore the declared Ubuntu policies

Run the companion as the normal user:

```sh
cd /home/groscoe/Projects/home-manager-config
nix run .#xps-host -- check
nix run .#xps-host -- apply
nix run .#xps-host -- check
nix run .#xps-host -- apply
```

The initial check can report drift on a fresh installation. Missing prerequisites,
an unsupported OS or unexpected file/link ownership must be resolved rather than
ignored. `apply` requests sudo interactively, backs up replacements, validates
the selected policy and requests only the necessary service actions. The second
apply must converge without new changes. Keep the printed backup/rollback paths.

Some fresh cloud images keep `/etc/ssh/sshd_config.d/50-cloud-init.conf` at mode
0600. Unprivileged inspection then stops with a permission error before applying
anything. Retain that protection. Build the bounded tool as the normal user and
inspect/apply its immutable executable with sudo instead:

```sh
cd /home/groscoe/Projects/home-manager-config
XPS_HOST_TOOL=$(nix build --no-link --print-out-paths --no-update-lock-file .#xps-host)
sudo "$XPS_HOST_TOOL/bin/xps-host" check
sudo "$XPS_HOST_TOOL/bin/xps-host" apply
sudo "$XPS_HOST_TOOL/bin/xps-host" check
```

The `apply` command also asks Ansible's become-password question; when the tool
already runs as root, no further elevation is needed. Press Enter at that
redundant BECOME password prompt; the guest tested this empty response and
converged successfully. Keep any actual sudo password in the terminal. The fresh guest exercises this privileged route using
only its synthetic account credential. Do not make private SSH fragments
world-readable merely to satisfy an unprivileged preflight.

This does **not** recreate xps's entire SSH server policy. It changes only X11
forwarding while retaining the server's other effective settings. In particular,
the VM still uses guest port 22. Real xps uses port 2222, key-only remote login,
no direct root login, and the deliberately retained agent/TCP forwarding policy.
Restore/review those server settings and all four authorized client keys
separately; keep the firewall and a second connection in mind before changing
SSH's port. The Mac's `xps` alias expects port 2222 and is not a bootstrap check
for a server still listening on 22.

The Nix startup helper replaces recognized installer links with persistent unit
files and preserves the separate `/nix` mount ordering. It does not change disk
configuration, restart the running Nix daemon, or alter firmware/boot images.

## 7. Build and activate the user profile

Use a real login as `groscoe`, with `/nix` mounted and Nix available. Do not run
Home Manager activation with sudo.

Before activation or restoring backup credentials, hold the two background
jobs that could scan or back up an incomplete restore. This is a temporary
recovery control, not normal production policy:

```sh
sudo touch /etc/home-recovery-in-progress
for unit in restic-backup.service clamav-scan.service; do
  sudo install -d -m 755 "/etc/systemd/user/$unit.d"
  printf '%s\n' '[Unit]' 'ConditionPathExists=!/etc/home-recovery-in-progress' |
    sudo tee "/etc/systemd/user/$unit.d/recovery.conf" >/dev/null
done
systemctl --user daemon-reload
systemctl --user stop restic-backup.service clamav-scan.service
```

The guest used this same condition/drop-in mechanism with its own test marker.
Unit timers can be enabled while the condition keeps their job bodies blocked.
Remove only these temporary files when the restore is verified (section 11).

```sh
cd /home/groscoe/Projects/home-manager-config
nix build --no-update-lock-file .#homeConfigurations.xps.activationPackage
./result/activate
```

Building is read-only with respect to the home configuration. Activation creates
the managed links/profile and adjusts user services. A cold build needs public
downloads and can compile local overrides, including Python; it can take much
longer than switching an existing installation with a populated store.

Home Manager should refuse to replace unmanaged existing files silently. On a
fresh Ubuntu account these can include files from `/etc/skel`; after restoring
data they can include old configuration files or links. Preserve and inspect
collisions, then use a deliberate Home Manager backup extension or move only
the reviewed files aside. Never resolve a collision with a blanket deletion of
the home directory or `.config`.

The fresh account's `.bashrc` collision was resolved with Home Manager's own
backup option, retaining the original file's exact SHA256 and leaving the lock
file unchanged:

```sh
cd /home/groscoe/Projects/home-manager-config
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
./result/home-path/bin/home-manager -b pre-recovery switch --flake .#xps
```

Use an unused backup suffix and retain those files until reviewed. Do not add
`force = true` merely to hide a collision. The cold build produced
`/nix/store/pzypf3nmk94p18v4zyk9xhjhswan51wp-home-manager-generation`, identical
to the generation active on the real xps during this rehearsal.

## 8. Login environment and desktop

Home Manager installs Fish; choosing it as the account's login shell is an OS
step. The existing xps uses `/home/groscoe/.nix-profile/bin/fish`. Register the
selected stable profile path in `/etc/shells` and use `chsh` deliberately after
the profile exists. Keep a working OS shell/console recovery route if `/nix`
cannot be mounted. Reopen a normal login and verify command resolution; do not
judge the new environment from an old shell with a cached PATH.

The configuration expects `en_US.UTF-8` and Ubuntu's locale archive. Verify
`locale -a` and generate the locale with Ubuntu's locale tools if missing.

Home Manager's i3 package needs an Ubuntu display-manager session entry. The
rehearsal used this public wrapper so SDDM can list the session even when the
user's home directory is private. Its actual execution runs as the user:

```sh
sudo install -m 755 validation/vm/hm-i3-session /usr/local/bin/hm-i3-session
sudo install -m 644 validation/vm/hm-i3.desktop /usr/share/xsessions/hm-i3.desktop
sudo systemctl enable sddm.service
sudo systemctl set-default graphical.target
```

Choose **Home Manager i3** at the next login. Start/restart SDDM only after
saving work: restarting a display manager ends graphical sessions. The wrapper
runs `/etc/X11/Xsession "$HOME/.nix-profile/bin/i3"`; Ubuntu's Xsession sources
the declared `.xsessionrc`, importing the HiDPI/display environment before i3.
The VM passed real SDDM password login through this bridge after reboot.

Polybar's current theme selects `DP-1-8`, falling back to `eDP-1`. These are
physical xps output names, not portable monitor identities. If neither exists,
the bar exits. Check `xrandr --query` and update the two monitor values in
`polybar/config/polybar/material/config.ini` for the new hardware, then build and
activate. The VM used a separate test copy selecting `Virtual-1`; the physical
profile was not silently changed. Battery/network modules can also need new
device names. Missing virtual battery, Wi-Fi or audio devices are not evidence
that their real hardware drivers work.

The wallpaper is user data at
`/home/groscoe/Pictures/Wallpapers/japan-temple-ultrawide.jpg`; restore it from
the personal backup or deliberately choose a different image. An absent
wallpaper is not repaired by installing the terminal or compositor.

The SSH agent's cached identities are memory state. Restore the private key,
start the declared agent and run `ssh-add` interactively when needed. If boot
startup of the user manager is wanted, review `loginctl enable-linger groscoe`
as a separate root account policy. The Fish hook preserves a valid forwarded
Mac agent and otherwise uses the local one. Keep key passphrases in the terminal.

## 9. Restore private data to staging first

Recover `/etc/restic-env`, `/etc/restic-password` and any backend authentication
from the independent copy. The repository password alone is insufficient if
the storage service also needs credentials. On xps these two files must be
root-owned and readable only by root plus the user's **private** group:

```sh
sudo chown root:groscoe /etc/restic-env /etc/restic-password
sudo chmod 640 /etc/restic-env /etc/restic-password
stat -c '%a %U:%G %n' /etc/restic-env /etc/restic-password
```

Do not print or commit their contents. These are trusted shell configuration,
so inspect their provenance before sourcing them. To use Restic interactively
without exposing values in output or command arguments:

```sh
set +x
set -a
. /etc/restic-env
set +a
restic snapshots --host xps
```

Choose an explicit snapshot by host, time, tags and included paths. Old xps
snapshots may contain only the home directory; the automatic configuration
expects home **and** `/vault`. Mac snapshots are not substitutes for xps ones.
Avoid an unqualified `latest` in this shared repository.

```sh
SNAPSHOT_ID=REPLACE_WITH_REVIEWED_SNAPSHOT_ID
restic ls "$SNAPSHOT_ID" /home/groscoe
restic ls "$SNAPSHOT_ID" /vault/.restic-protected
umask 077
RESTORE_STAGE=$(mktemp -d /home/groscoe/recovery-restore.XXXXXXXX)
restic restore "$SNAPSHOT_ID" --target "$RESTORE_STAGE" \
  --include /home/groscoe/.ssh \
  --include /home/groscoe/.gnupg \
  --include /home/groscoe/Projects \
  --include /vault/.restic-protected
```

Replace/extend the includes deliberately for documents, browser/application
profiles, photos, music and the rest of `/vault`. A full restore needs enough
additional disk space for staging; the VM's small synthetic restore does not
measure production restore capacity or time. Inspect the restored directory
tree before copying anything into the live home. Restic recreates original
absolute paths beneath the target, e.g. `$RESTORE_STAGE/home/groscoe/...`.

The current backup excludes Home Manager links still pointing at installed
managed files. Let activation recreate those links. Restore application data
and locally replaced files selectively; old absolute `/nix/store` links may
refer to absent paths. Check for collisions before the next activation.

Preserve SSH/GPG directory and file permissions. Import GPG keys/trust or
restore their private data while the agent is stopped; do not copy stale agent
sockets. Restore the four approved `authorized_keys` entries and confirm the
Mac key works in a second SSH connection before ending the first. Load an SSH
identity with `ssh-add` after login; an agent service does not retain unlocked
keys through reboot.

Important coverage limits:

- `.git`, caches, dependencies and selected build/download outputs are excluded.
  Fetch published Git history again; separately recover unpublished commits.
- `/nix`, `/etc`, `/var/lib/docker` and data on unlisted filesystems are not
  covered by the ordinary home-plus-vault job. `--one-file-system` is intentional.
- Dropbox's `.dropbox` and `.dropbox-dist` are excluded. Expect to sign in and
  resync; do not promise restored authentication from this backup.
- Browser credentials, OS keyrings, account sessions and Tailscale identities
  have their own state/enrollment requirements. Applications being installed
  does not prove those accounts are recoverable.
- `restic check` verifies repository structure; `--read-data` reads all stored
  data and can be expensive. The rehearsal ran `check --read-data` on its small
  local synthetic repository, not on the production repository.

See the [Restic restore documentation](https://restic.readthedocs.io/en/stable/050_restore.html)
for selection details. Always retain staging until contents and permissions have
been checked; restoring directly over the running home can replace live files.

## 10. Restore the protected exports

`/vault/.restic-protected` contains private tar archives and `manifest.json` for
three configured sources: work Tailscale state, the Desktop LUKS-header backup,
and the stopped Onebus PostGIS directory. The personal Tailscale state remains
ordinary user data. Match the manifest's source paths and archive names to the
chosen snapshot; do not assume an old snapshot contains all three.

The archives preserve **numeric** ownership and modes. Listing their contents
does not require changing the protected originals:

```sh
tar --list --verbose --numeric-owner --file /PRIVATE/STAGING/PATH/SELECTED.tar
```

Review member names and link targets before privileged extraction. They should
correspond only to the source named in that archive. Reject absolute paths,
`..` traversal, unexpected links/devices or unrelated paths. Extract only a
trusted, reviewed archive into a new empty root-private staging directory:

```sh
PROTECTED_STAGE=$(sudo mktemp -d /var/tmp/xps-protected-restore.XXXXXXXX)
sudo tar --extract --file /PRIVATE/STAGING/PATH/SELECTED.tar \
  --directory "$PROTECTED_STAGE" --numeric-owner --same-owner --same-permissions
```

Inspect the staged tree using sudo. Compare representative contents, ownership
and modes with the manifest/old inventory. Copy only the intended source tree
into its final destination, preserving ownership and permissions and keeping
the associated service stopped. Review numeric UID/GID mapping on a different
computer; UID 999 is not universally the PostgreSQL account.

For Onebus, retain the cold data until a compatible PostgreSQL/PostGIS version
can read it. A successful tar round trip does not prove database engine
compatibility, extension availability or logical consistency. Take a logical
database dump before a planned migration whenever possible. The exporter
deliberately refuses a running `onebus-postgis` container; do not bypass that
guard to obtain a live-filesystem copy.

For Tailscale, restore each identity before installing/starting its daemon.
Avoid running the old and replacement machines simultaneously with the same
identity. Re-enroll intentionally if retaining the old identity is inappropriate.
The synthetic rehearsal verified protected state bytes/metadata, not real
Tailscale authentication.

The Desktop LUKS-header **file** is recovery material, not an instruction to
write it onto a disk. Restoring a header to an encryption device is a separate,
device-specific operation requiring the correct volume identity and a reviewed
recovery plan. This guide does not perform it.

## 11. Restore the privileged helpers and schedules

Before installing the exporter, restore all three configured source paths.
Ubuntu's `/usr/bin/docker` and daemon must be installed, and the real
`onebus-postgis` container must exist and be stopped. Recreate it from the
preserved project's compatible image/volume definition before starting it;
verify `sudo docker inspect --format '{{.State.Running}}' onebus-postgis`
returns `false`. A missing container also fails this guard. The VM's BusyBox
container was a synthetic refusal-test fixture, not a PostgreSQL recovery.

After private source data, the stopped container and `/vault` are ready, run the
declared root export installer:

```sh
~/.local/bin/install-restic-backup-export
sudo systemctl status restic-protected-export.timer --no-pager
sudo systemctl start restic-protected-export.service
sudo journalctl -u restic-protected-export.service -n 40 --no-pager
```

It requests sudo, verifies its backup, installs root-owned code/units and starts
an export. It does not upload data or modify source permissions. The existing
private export directory must have the expected root/private-group ownership;
resolve mismatches rather than making secrets public. The user backup requires
a complete export less than 26 hours old. Reinstall after changing the declared
protected-source list. Save the printed rollback path.

For VNC on the actual Intel xps, run `install-xps-backlight-access` once after
checking that `/sys/class/backlight/intel_backlight` is the correct device. It
grants the private primary group narrow write access to that brightness
attribute, preserves metadata and prints rollback. It leaves brightness
unchanged. Another computer needs a reviewed hardware profile; the VM has no
physical backlight and cannot validate this installer on hardware.

When restoration and the protected export are complete, remove the temporary
job holds introduced in section 7, then validate manually before relying on the
timers:

```sh
sudo rm /etc/home-recovery-in-progress
sudo rm /etc/systemd/user/restic-backup.service.d/recovery.conf
sudo rm /etc/systemd/user/clamav-scan.service.d/recovery.conf
systemctl --user daemon-reload
restic-backup --dry-run
restic-backup --run
restic-backup --status
systemctl --user list-timers --all
```

Read errors are failures, not reasons to silently add exclusions. The first run
or a large change may request confirmation; scheduled runs do not bypass the
20 decimal GB gate. No automatic prune job is configured. Preserve the `archive`
tag and the dedicated archive snapshot documented in `restic-backup/README.md`.

ClamAV also needs Ubuntu's scanner/signatures and its updater, independently of
the user timer. Confirm signature updates before enabling real scans. The
intended setup keeps the resident daemon/socket disabled and runs low-priority
scans of Downloads, Desktop and `/vault`, excluding caches, on AC. Inspect
`journalctl --user -u clamav-scan.service`; detected files are not deleted.
The VM did not perform a real antivirus scan or download production signatures.

## 12. Networking, the two tailnets and remote desktop

Restore or clone the separate infrastructure repository at
`/vault/mlabs/code/liqwid-infra`, retaining its lock file. Its
`TAILSCALE.md` is the detailed operational reference. Preserve its working tree
as well as published history: at rehearsal time this separate checkout had
local `TAILSCALE.md` edits outside the Home Manager repository. Do not assume
a remote clone includes unpublished files or commits. Both saved state directories
must exist before its installer runs:

```sh
cd /vault/mlabs/code/liqwid-infra
nix build .#install-services .#services .#status
nix run .#install-services
nix run .#status
```

Use `--offline` only after those dependencies are available. The installer
preserves the identities/preferences, requests sudo, creates rollback material
and enables both units after their required mounts:

| Connection | Unit / state | Network and DNS role |
| --- | --- | --- |
| Work/global | `liqwid-tailscale-global.service`; `~/.local/state/liqwid-infra/global` | Root daemon, `lqwd-ts-global` tunnel, owns tailnet DNS |
| Personal/local | `liqwid-tailscale-local.service`; `~/.local/state/liqwid-infra/local` | User-owned system service, userspace networking, declines host DNS |

The installer integrates NetworkManager with `systemd-resolved` and uses the
resolved stub for `/etc/resolv.conf`. Preserve this arrangement; do not replace
it with a static Tailscale-only resolver. Inspect both `BackendState`/tailnets
and public DNS: active systemd units alone are insufficient.

Firewall/Docker policy is not recreated by `xps-host`. Restore/review it before
starting remotely reachable services. Intended access remains SSH/Mosh/SSHFS
from the home LAN and both tailnets, Jellyfin/Buzz from the LAN and **personal**
tailnet only, and development/database services local unless explicitly opened.
Docker's own forwarding rules and personal userspace Tailscale's local forwarding
guard need their protected configuration too. Never substitute a broad allow
rule for those interface/source restrictions. Validate the actual allowed and
denied network paths from another machine; no real tailnet was joined in the VM.

Codex remains an intentional npm-managed exception. The profile declares Node
and the user prefix (`~/.npm`); restore/install the desired npm CLI separately
with `npm install -g @openai/codex`, then authenticate interactively. Do not put
tokens in Nix. Project environments remain project-owned and were not migrated
or validated by this rehearsal.

For XPS Desktop, first log in to the local i3 session, then create a new private
VNC credential with `xps-desktop-control password` (or restore the private state
file). Launch **XPS Desktop** on mbp after SSH itself works. It shares the
existing desktop over the SSH-tunnelled Unix socket; it does not supply BIOS,
early disk unlock or SDDM access. Test remote password unlock, Command+Enter,
clipboard and redraw speed. During sharing Picom stays running in bypass mode
and the hardware backlight is zero; disconnect must restore the previous display
state. See `xps-desktop/README.md` for its diagnostics and timeout behavior.

## 13. Acceptance, reboot and rollback

Do these before declaring the new installation recovered:

```sh
cd /home/groscoe/Projects/home-manager-config
nix flake check --no-update-lock-file --show-trace
sudo /usr/bin/python3 -I hosts/xps/ubuntu/nix_startup.py check
systemctl --user is-active ssh-agent picom dunst xsettingsd polybar
command -v python3 pip pip3 jupyter alacritty rofi tmux
python3 --version
python3 -m pip --version
pip --version
getent passwd groscoe
systemctl --user list-timers --all
```

Use the actual Jupyter kernelspec interpreter when checking notebook libraries;
global Python and the managed notebook environment intentionally have different
compatible versions. Run a notebook that imports the declared libraries, reads
and writes CSV/Excel/Parquet and renders both a saved and inline chart. Create
a new `python3 -m venv` and verify its own pip. Compile/link/run a small program
in both `nix develop .#c` and `nix develop .#c-clang`.

Reboot normally, unlock the real volumes and log in again. Verify `/nix` and
`/vault` are mounted, `nix store info --store daemon` succeeds, and inspect
`systemd-analyze critical-chain nix-daemon.socket`. Recheck both tailnets, DNS,
Docker, SSH/Mosh from the Mac, the local/forwarded agent behavior and timers.
Reapply `xps-host` and the same Home Manager generation; there should be no new
policy changes or unmanaged-file collisions.

Keep the working profile and root-policy backup paths until acceptance passes.
For user-profile rollback, find the previous immutable activation path with
`home-manager generations` and run that generation's `activate` as the user.
Do not garbage-collect it first. The rehearsal activated a small synthetic
variant, returned to the original generation and confirmed its extra file was
removed, then reactivated the original successfully.

For root policies, use the exact scope/rollback command printed by their
installer. The standalone Nix helper can restore its saved definitions and
reconverge using Ubuntu Python even with the Nix daemon stopped:

```sh
# Use the exact backup path printed during that installation.
sudo /usr/bin/python3 -I /var/backups/xps-nix-startup-EXACT/nix_startup.py \
  rollback /var/backups/xps-nix-startup-EXACT
sudo /usr/bin/python3 -I hosts/xps/ubuntu/nix_startup.py check
sudo /usr/bin/python3 -I hosts/xps/ubuntu/nix_startup.py apply
sudo systemctl start nix-daemon.socket
```

`check` may return 1 for recognized drift after rollback. Unexpected types,
ownership or later administrator changes are refusal conditions, not something
to force past. If `/nix` is unavailable, obtain the independently retained source
and use an Ubuntu shell/Python; a Fish binary stored under `/nix` cannot solve
a missing mount. The helper repairs definitions, not a lost Nix store/database.

Enroll the supported reader as the user with `fprintd-enroll -f right-index-finger`
and verify it with `fprintd-verify` before testing fingerprint login. The declared
hint names that finger. A normal password should still work when the reader is
absent or fails. Enrollment/templates are deliberately outside Git.

Physical acceptance is still required for fingerprint/password fallback in
SDDM and i3lock, suspend/resume, actual Intel/NixGL graphics, cursor/HiDPI,
backlight restoration, IPU6 camera, Wi-Fi, Sony left/right audio, and VNC latency.
Run these with a working SSH/console recovery route. A VM's software display or
mock fingerprint conversation is not a hardware test.

## 14. Mac scope

This rehearsal restores **xps**, not macOS. The canonical repo also declares
mbp's Home Manager, nix-darwin and existing Homebrew policy. The native Mac
flake checks build those profiles without activating them; they do not perform
a fresh macOS install, restore Keychain/TCC or prove every Homebrew download.

On an already bootstrapped Mac, the known activation command remains:

```sh
sudo -H /run/current-system/sw/bin/darwin-rebuild switch \
  --no-write-lock-file --flake /Users/groscoe/Projects/home-manager-config#mbp
```

Restore Mac private data separately and grant Full Disk Access to the actual
terminal/background backup context through macOS. Manual iTerm access and
launchd access must each be tested. Read `restic-backup/README.md` for the tested
photo-library permission issue. Do not copy Linux PAM, systemd, UID/GID mappings
or `/home` paths to macOS.

## 15. Rehearsal evidence and known failures

The baseline was signed commit `4c41de134709a73ae7fce0fce81f45d0a36f1580`,
lock SHA256 `15138e7def3305caed4708d1e7484def88e4f92c6f7355df8e67aff4c476bd6a`.
The only baseline source correction during the guest test was increasing a
bounded Ansible **fixture** timeout from 120 to 300 seconds and retaining its
partial output on timeout; assertions and production settings were unchanged.
That correction is included with this guide.

The dated Ubuntu image was
`https://cloud-images.ubuntu.com/jammy/20261020/jammy-server-cloudimg-amd64.img`,
SHA256 `2099e63da0b822ef8e05e3d596c1b402eaaae658fc08ab919cb8495bfcdc488b`.
Its SHA256SUMS signature was checked with Ubuntu's installed cloud-image keyring,
signer `D2EB44626FDDC30B513D5BB71A5D6C4C7DB87C81`. This dated URL may eventually
be retired; select and verify a new dated image deliberately instead of silently
treating `latest` as the same test.

The unprivileged QEMU/KVM guest used UEFI, 4 vCPU, 8 GiB RAM and sparse virtual
24/96/8 GiB root/Nix/vault disks on internal `/home`. Its SSH forward was loopback
only and its console/QMP used private Unix sockets. It had generated test keys
and credentials, no host mounts, no production identities, and no host agent
forwarding. Public downloads used ordinary user-mode NAT; that mode permits
outbound LAN access and is not an isolation claim. The external SSD was inspected
read-only and was never written or formatted.

| Check | Actual result / limit |
| --- | --- |
| Fresh cloud-init / Nix | Passed with Nix 2.34.9 and separate real guest mounts |
| Cold full profile builds | Passed twice: 1,449.78 s and 1,359.38 s; independent fresh guests, public caches plus local builds, no host store import/share |
| Resulting profile | Exact physical-xps generation `pzypf3nmk94p18v4zyk9xhjhswan51wp` |
| Native flake checks | Passed on both hosts; Linux includes 58 personal regressions, 17 PAM cases, 16 Nix startup cases, real Ansible fixtures and 11 VM boundary tests |
| Root policy | Apply/check passed; second apply `changed=0` |
| Collision handling | Initial `.bashrc` refusal preserved; backup-option activation retained the original exact digest |
| Reboot/startup | Passed on separate `/nix`; daemon store query and a new tiny build passed, including isolated networking |
| Offline acceptance | Outbound TCP blocked; loopback SSH, local build and unchanged-profile activation passed; populated store, not a fresh offline install |
| Policy rollback | Saved Nix definitions restored, drift detected, native repair with daemon stopped passed |
| Home Manager rollback | Synthetic generation activated, original restored, fixture file removed, reactivation passed |
| Login / desktop | Real SDDM password login and i3lock password unlock; i3, Alacritty, Picom, Dunst, Xsettings, Rofi and tmux ran |
| Polybar | Passed with explicitly recorded virtual-monitor test override; original hardware names failed in VM |
| Python / pip | Fresh login: Python 3.15.1 / pip 26.2.2 matched; new venv worked |
| Jupyter | Python 3.14.7 kernel executed synthetic exploration notebook; NumPy/pandas, CSV/Excel/Parquet, Plotly widget, saved PDF/PNG and inline chart passed |
| C environments | GCC 16.2.0 and Clang 21.1.8 built an Autotools/Libtool project and ran it under GDB |
| Backup / restore | Local synthetic repository, explicit snapshot restore, `check --read-data`, file bytes and protected numeric ownership/modes passed |
| Backup refusal/defer cases | Running dummy database and unreadable source refused; missing `/vault` deferred; no new snapshot or last-success change on unsafe attempts |
| Actual database / private restore | Not tested; fixture bytes were not a real PostgreSQL cluster |
| Real hardware / tailnets | Not tested by the VM; retain the physical acceptance list |

Failures that changed the recovery recipe, retained in private evidence:

1. Cloud-init omitted root `HOME`; upstream Nix installer stopped. Set root's
   actual home explicitly, then started a completely fresh guest.
2. SSH became reachable before bootstrap finished. Added bounded identity-checked
   readiness; authentication/host-key failures are not retried as boot delays.
3. The Ansible fixture exceeded 120 seconds on the constrained VM. Raised only
   that bound to 300 seconds and retained partial logs. The full fixture passed.
4. A root-only cloud SSH fragment prevented unprivileged inspection. Used the
   immutable built companion via sudo; did not weaken file permissions.
5. Fresh `.bashrc` collided as intended. Used Home Manager's backup extension,
   verified the original digest and kept `flake.lock` unchanged.
6. The initial VM directory was under backed-up `.local/state`. Moved the owned
   disposable state into already excluded `.cache` while the VM and backup job
   were stopped; verified the same base image and overlay consistency.
7. The cloud kernel lacked the default emulated VGA driver. Virtio GPU worked;
   this is a guest graphics prerequisite, not an Intel driver replacement.
8. SDDM needed a public session wrapper; Polybar needed virtual monitor names.
   A missing wallpaper remained an explicit personal-data prerequisite.
9. The repeat found a harness race: `reset-failed` can reject a Polybar unit
   before it has been loaded. The harness now resets only an actually failed
   unit, then starts it and requires an active result. Production policy did not
   need changing.
10. Locking all sessions from SSH required authorization. The test uses sudo
    inside the guest for that control action, then verifies normal password
    unlock. It changes no authentication policy.
11. An offline test initially tried the public binary cache despite having
    enough local build inputs. Added explicit `--offline`; the tiny derivation
    then built locally, and the exact home generation reactivated without
    outbound networking.
12. Headless QEMU screenshots were stale until a private RFB client requested a
   framebuffer update. Login/process checks and a refreshed screenshot confirmed
   the actual desktop; an initial black screenshot alone was not a login failure.

Pinned sources still depend on their downloads remaining available. Retain the
verified installer, lock file and source revision independently. A future offline
recovery kit should also retain and test a trusted binary cache of the required
closure; that export/import workflow was not rehearsed here. Offline reboot and
activation of an already populated guest do not prove a fresh offline install.

The compact non-secret report is
[`validation/vm/results/2026-10-24.json`](validation/vm/results/2026-10-24.json).
Its Ubuntu package inventory records the bootstrap state; later Docker/X11 test
packages are listed separately in the report. Failed attempts remain recorded
alongside their successful retries, rather than being replaced with all-green
summaries.

The reusable controller and reproduction commands are in
[`validation/vm/README.md`](validation/vm/README.md). Its generated credentials,
cloud seed, private logs and VM disks belong only in the private excluded cache,
never in Git. Keep the non-secret report alongside the exact source revision.

## Hardware health tracking added after the VM rehearsal

The monthly battery/NVMe tracker was added on 2026-10-27, after the
2026-10-24 fresh-VM rehearsal above. Its synthetic regressions and native
host checks are separate validation; the recorded VM-generation hashes above
still describe the earlier rehearsal. See [hardware-health/README.md](hardware-health/README.md)
for configuration, alert thresholds, notification delivery and history.

On a recovered laptop, verify `services.hardware-health.devices` against the
actual internal NVMe controller before enabling unattended reads. On Linux,
install native smartmontools and explicitly run
`~/.local/bin/install-hardware-health-access`; this grants only the declared
identification/health query and prints a rollback path. macOS needs no root
SMART helper. Run `hardware-health --record` and
`hardware-health --test-notification` in the real login session, then check
`hardware-health --status`. A blank VM has no physical battery/NVMe controller;
exclude this hardware-only service when creating its dedicated profile.

Restore `~/.local/state/hardware-health` with the user's home to preserve
trends. Replacement hardware is identified separately, so previous-device
readings do not create false decline alarms. The Mac's optional xps report
relay needs its SSH destination/path updated if the address or username changes.
