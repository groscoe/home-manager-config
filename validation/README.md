# Configuration validation and restore rehearsal

The target is a reproducible working machine, including its private state. A
successful Nix build proves only part of that. Use these four levels and record
which actually passed. The 2026-10-24 fresh Ubuntu rehearsal and recovery
procedure are recorded in [RECOVERY.md](../RECOVERY.md).

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
| `vm-home-profile` | Yes | — | Complete guest profile with the explicit QEMU hardware descriptor |
| `hardware-profiles` | Yes | — | Generated hardware wiring, optional device omission, virtual tmux prefix and isolated XRandR restoration |
| `xps-host` | Yes | — | Synthetic PAM authentication, Nix unit replacement/rollback and Ansible convergence tests |
| `restore-vm` | Yes | — | Controller filesystem/identity/network boundaries; does not boot a VM |

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

## 3. Disposable Ubuntu restore rehearsal

The 2026-10-24 test used a fresh signed Ubuntu 22.04 cloud image, synthetic
separate `/nix` and `/vault` volumes, generated credentials and no shared host
store/home. The cold xps profile build reproduced the physical machine's exact
Home Manager generation. Activation, root-policy convergence, Nix startup repair,
reboot, user-generation rollback, notebook/C tooling, virtual desktop and local
synthetic backup/restore were exercised. Hardware-name adaptations and failures
are recorded rather than hidden.

See [RECOVERY.md](../RECOVERY.md) for commands, measured results, private-state
recovery and limitations. [The VM controller](vm/README.md) provides pinned tools
and guarded repeatable stages. A full VM run is explicit, resource-intensive and
separate from lightweight native flake checks. It does not install or activate
anything on the physical host. Real secrets, databases, disk encryption, tailnet
connectivity, hardware and a fresh macOS restore remain separate acceptance work.

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
| Python and development | Run a synthetic Jupyter notebook that imports the declared data libraries, reads CSV/Excel and renders a chart; verify Python/pip pairing. Compile, link and run a tiny program in both declared C shells using temporary files. The synthetic VM checks these application behaviors; they remain separate from ordinary flake checks. |
| Recovery | Restore representative private settings/data to a separate destination and compare contents/permissions; keep repository password independently recoverable |

VMs cannot prove these hardware behaviors. Configuration tests also cannot
recreate secrets or device enrollment. A real backup restore needs a deliberate
separate run with credentials; the automatic regression tests only use fixtures.
