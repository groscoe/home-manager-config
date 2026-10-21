# Home Manager configuration

One source tree serves two explicit hosts:

| Host | Platform | Home profile | System profile |
| --- | --- | --- | --- |
| `xps` | `x86_64-linux` (Ubuntu) | `homeConfigurations.xps` | Existing Ubuntu configuration, outside this flake |
| `mbp` | `aarch64-darwin` | `homeConfigurations.mbp` | `darwinConfigurations.mbp` |

`home.nix` contains shared user settings. `hosts/xps/home.nix` owns the XPS
scaling, Linux services, backup roots and protected exports. Its overlay retains
the selected Firefox, VSCodium and signature-tool packages. `hosts/mbp/home.nix`
owns the Mac backup scope and XPS Desktop launcher settings;
`hosts/mbp/system.nix` contains its existing nix-darwin and Homebrew configuration.
The XPS-specific Fish key bindings are kept in its host directory.

`hosts/xps/session.nix` also owns the persistent SSH-agent Fish hook and packages
`xps-x-settings`, which i3 runs at login/reload. The keyboard policy retains the
ABNT-2 layout, Caps→Escape and the existing keycode-20 override. Attached Wacom
styluses retain their counterclockwise rotation and tablet area; no tablet is
required. The command declares its X11/Wacom tools through Nix rather than relying
on a separate `~/Projects/x-settings.sh` or Ubuntu-installed client utilities.
The Fish hook preserves a working forwarded agent and falls back to the local
agent only when its socket is missing. SSH keys and agent identities remain state
outside the repository.

## SSH and personal helpers

`ssh/` enables Home Manager's SSH configuration without replacing the OS client.
The host modules retain the Mac's Keychain/Ed25519 defaults and agent forwarding
to xps, and xps's GitHub alias/RSA key selection. Only key paths are declared;
private keys, known-host history, agent identities and credentials remain outside
the Nix store and must be restored separately.

`helpers/` packages `file-preview` and `dice`, including their interpreters and
preview dependencies. Fish and Zsh's file search and the Bash/Zsh dice function
use these commands without requiring files in `~/Projects`. `file-preview`
handles directory trees, images, the first ten PDF pages and text. `dice` accepts
no arguments (1–6), one upper bound, or an inclusive lower/upper bound.

The xps profile also manages the existing `agent` and `cursor` launchers and its
`.xprofile`. Cursor's vendor-updated `~/.local/bin/cursor-agent` installation and
login state require separate restoration. The login hook reuses the persistent
SSH agent; scaling is owned by `.xsessionrc`. The old duplicate scaling setting,
per-login agent spawning and unavailable `wal` command are retired.

The unused Teams coffee-break automation and old audio, webcam, speech,
mouse-movement and lock/suspend helpers were retired after private backups.
Their Teams shell shortcuts are removed as well. Third-party Python CLI
entrypoints in `~/.local/bin` and separate project-specific scripts still need
individual application/environment review.

## Package pins

The consolidation preserves the previously different package sets:

- `nixpkgs`: XPS base revision `3f05c8657c7016fb8cfec9ca06dac066cdeddb91`.
- `nixpkgs-darwin`: Mac base revision `0921fdb3e13e40fe25fbc52b89661a9d6d32ac68`.
- `nixpkgs-unstable`: the existing selected Linux packages.
- `nixpkgs-stable`: the existing auxiliary package set, including Fish on macOS.

All are pinned in the single `flake.lock`. Update a particular input intentionally
with `nix flake update INPUT`; consolidating the sources does not update packages.
The Mac's full Homebrew list is retained. The Codex package source in `codex/`
is preserved from the Mac checkout, but is not re-enabled on Linux.

## Apply on xps

Install Nix with flakes enabled and clone this repository, then:

```sh
nix build .#homeConfigurations.xps.activationPackage
./result/activate
```

An installed Home Manager CLI can instead use:

```sh
home-manager switch --flake .#xps
```

This assumes the existing Ubuntu prerequisites. It does not install the OS,
configure mounts, PAM/SDDM, firewall rules or the separate Liqwid tailnet services.
The backlight-access and protected-export installers described in their modules
remain explicit one-time root setup steps.

## Apply on mbp

For the existing nix-darwin installation:

```sh
sudo -H /run/current-system/sw/bin/darwin-rebuild switch \
  --flake /Users/groscoe/Projects/home-manager-config#mbp
```

For first bootstrap after installing Nix:

```sh
sudo -H nix run github:LnL7/nix-darwin/nix-darwin-25.11#darwin-rebuild -- \
  switch --flake /Users/groscoe/Projects/home-manager-config#mbp
```

The standalone home profile is also available as
`.#homeConfigurations.mbp.activationPackage`; it does not apply system/Homebrew
settings. Choose the intended scope rather than alternating the two methods
without checking the active profile.

## Validate without activating

```sh
nix eval .#homeConfigurations.xps.activationPackage.drvPath
nix eval .#homeConfigurations.mbp.activationPackage.drvPath
nix eval .#darwinConfigurations.mbp.system.drvPath
```

Build the appropriate home activation package on its native host before applying
it. Building produces an artifact; only activation changes the running setup.

Legacy targets `groscoe`, `groscoe-linux`, `groscoe-darwin` and `groscoe-macos`
remain aliases for compatibility. The per-platform default packages remain.
New documentation and scripts should use the host names.

## Source and recovery

Commit changes from either machine to this same repository, then pull them on the
other. Put shared preferences in the common modules and machine-specific policy
in its host profile; do not maintain different `home.nix` or lock files per clone.
Private keys, passwords, application databases and device enrollment remain
outside the Nix source and need their documented recovery paths. See
`restic-backup/README.md` and `xps-desktop/README.md` for those modules' setup/state.

The 2026-10-21 consolidation retains XPS's existing commit history and both
working trees' changes. Full pre-consolidation source/Git snapshots and the
comparison results are kept outside this repository in the Codex audit workspace.
Neither system is activated merely by synchronizing this source tree.
