# Configuration validation and restore rehearsal

The target is a reproducible working machine, including its private state. A
successful Nix build proves only part of that. Use these four levels and record
which actually passed; a fresh OS restore has not yet been demonstrated.

## 1. Native builds and regression tests

From the repository root on **each** machine:

```sh
nix flake check --no-update-lock-file --show-trace
```

This builds the current platform's `checks` without activating a generation:

| Check | xps | mbp | What it covers |
| --- | --- | --- | --- |
| `home-profile` | Yes | Yes | Full Home Manager activation package, applications and generated configuration |
| `system-profile` | — | Yes | Full nix-darwin build; does not run its Homebrew activation |
| `personal-scripts` | Yes | Yes | Existing Restic, XPS Desktop and Alacritty regression suites |
| `xps-host` | Yes | — | Synthetic PAM authentication, Nix unit replacement/rollback and Ansible convergence tests |

`personal-scripts` uses a private temporary home, synthetic local Restic
repositories, fake display/backlight state and loopback sockets. No real
credentials, backup repositories, X server or system services are used. Restic
must be present, so missing dependencies cannot silently skip integration tests.
In the fixture copy only, the loader's `/usr/bin/env` is replaced with Nix's
equivalent because Linux build sandboxes lack that OS path. The installed loader
still uses the Ubuntu/macOS utility.
Only the three protected-export descriptor tests are skipped on macOS because
they require Linux `/proc/self/fd`; they run on Linux. Its output is a JSON
test report, available separately with:

```sh
nix build --no-link --print-out-paths .#checks.x86_64-linux.personal-scripts
# On mbp, replace x86_64-linux with aarch64-darwin.
```

To evaluate both platforms without building foreign binaries:

```sh
nix flake check --all-systems --no-build --no-update-lock-file
```

Run native checks before committing and after changing the lock file. A future
CI job can use the same command on Linux x86_64 and macOS arm64 with no secrets
or activation. No hosted jobs are configured here. Nix may reuse successful
builds whose inputs have not changed; this is not an empty-store download test.

## 2. Read-only checks on the installed host

On xps:

```sh
nix run .#xps-host -- check
```

This compares the **declared subset** of Ubuntu policies with the installed
files. See [host policy instructions](../hosts/xps/ubuntu/README.md) for its scope,
the optional Ansible check mode and the separate Qt/SDDM theme test. It neither
applies policies nor proves that every OS prerequisite has been declared.

When a home profile really needs activation, save the current generation and
check Home Manager's collision checks first. Then activate deliberately and
check the affected application/service. Building a package alone cannot prove
that existing dotfiles, login hooks, or the desktop session work after activation.

## 3. Disposable Ubuntu restore rehearsal — not yet run

Use an x86_64 Ubuntu 22.04 guest first, matching the current base OS. Keep the
LTS migration separate so failures have a clear cause. This is a guest-only
exercise; it must not be run against xps's disks.

1. Download the official cloud image and verify its signed checksum. Use a
   disposable QCOW overlay and cloud-init seed, with a test `groscoe` account
   (UID 1000), fresh SSH key and throwaway passwords. Bind guest SSH forwarding
   to `127.0.0.1` and use a separate known-hosts file. Do not attach host block
   devices, the real home/vault, biometric data, SSH/GPG private keys, Tailscale
   identities or backup credentials.
2. Install multi-user Nix and explicitly record the required Ubuntu packages,
   repositories and services. Clone the exact reviewed commit and keep its
   `flake.lock`. Mount a synthetic `/vault`; exercise a separate synthetic
   `/nix` filesystem when testing Nix's mount ordering. Do not reuse real disk
   identifiers, encrypted volumes or their unlock configuration.
3. Run the native flake checks in the guest. Inspect `xps-host check`, apply its
   policies **inside the guest**, then apply again. The second apply must report
   no changes. Test the documented rollback and converge again. Save the logs.
4. Activate the xps home profile **inside the guest** from an empty home. Check
   that there are no unowned-file collisions and the declared commands resolve.
   Start i3 with a virtual display and exercise the terminal, Rofi menus, status
   bar, notification server and fonts. Check generated SSH settings without
   connecting to production hosts.
5. Use synthetic files to exercise backup, preflight refusal, scheduled retry,
   sample restore and protected exports. Use a guest-only stopped database
   fixture; never import the production database or Restic credentials.
6. Reboot the guest. Check the Nix socket/daemon and their mount ordering, login
   environment, user services and expected timers. Confirm declared host files
   still match and a second activation converges. Recreate the guest from
   scratch with only these instructions and the recorded prerequisites.

Record the source commit, lock-file hash, Ubuntu image checksum, installed
package versions, commands, failures and logs. A successful rehearsal means the
guest was rebuilt without borrowing undeclared files from the live laptop.
Also perform an empty-store build to catch unavailable sources or credentials
hidden by caches. The current repository is **not** yet a complete Ubuntu
bootstrap: package/repository setup, Nix installation/settings, mounts, firewall,
some privileged helpers and private-state recovery still need explicit coverage.
Missing prerequisites found here should become declarations or documented
intentional exceptions before claiming painless OS recovery.

References: [Nix flake check](https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-flake-check),
[Ubuntu QEMU images and overlays](https://ubuntu.com/docs/public-images/public-images-how-to/launch-qcow-with-qemu/),
[signed image checksums](https://ubuntu.com/docs/public-images/public-images-reference/artifacts/).

## 4. Physical xps acceptance

After a relevant activation or OS restore, test the affected rows with the actual
device. Keep a working SSH session and known rollback generation while testing.

| Area | Acceptance |
| --- | --- |
| Login and power | Password and fingerprint in SDDM/i3lock, then suspend/resume; correct authentication guidance |
| Desktop | HiDPI/cursor, ABNT-2/Caps mapping, Alacritty typing/scrolling, Picom, Polybar, Rofi and notifications |
| XPS Desktop | Mac keyboard/mouse, remote password unlock, comfortable redraws; dark hardware backlight while connected; original brightness and compositor mode restored after disconnect/failure |
| Hardware | Webcam preview, Sony stereo left/right, Wi-Fi and Bluetooth menus; real graphics acceleration |
| Network | Both tailnets and DNS; SSH/Mosh/SSHFS from authorized LAN/tailnets; Jellyfin/Buzz access only from the intended networks |
| Shell | Local versus SSH tmux prefix, clipboard on the Mac, persistent local agent and forwarded agent behavior |
| Python and development | Run a synthetic Jupyter notebook that imports the declared data libraries, reads CSV/Excel and renders a chart; verify Python/pip pairing. Compile, link and run a tiny program in both declared C shells using temporary files. These application-level checks are not yet flake checks. |
| Recovery | Restore representative private settings/data to a separate destination and compare contents/permissions; keep repository password independently recoverable |

VMs cannot prove these hardware behaviors. Configuration tests also cannot
recreate secrets or device enrollment. A real backup restore needs a deliberate
separate run with credentials; the automatic regression tests only use fixtures.
