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
`.xprofile`. The xps application module also supplies `cursor-agent` from the
pinned package; Cursor's login state requires separate restoration. The login hook reuses the persistent
SSH agent; scaling is owned by `.xsessionrc`. The old duplicate scaling setting,
per-login agent spawning and unavailable `wal` command are retired.

The unused Teams coffee-break automation and old audio, webcam, speech,
mouse-movement and lock/suspend helpers were retired after private backups.
Their Teams shell shortcuts are removed as well. The notebook/PDF/SQL tools now
use the isolated environment described below; the existing OpenAI CLI and
project-specific scripts remain outside Home Manager.

## xps applications and command-line tools

`hosts/xps/applications.nix` owns xps's additional user applications through the
existing `nixpkgs-unstable` input. It declares Git and Git LFS, curl/wget/rsync,
FFmpeg, Pandoc, htop, PostgreSQL 14 client tools, SQLite, Python yq, network/file-watching
utilities, ZIP tools, Meson/Ninja and Cursor CLI. PostgreSQL is kept on the
installed major version; declaring its package does not enable a database service.
The selected packages do not change the Mac profile or its Homebrew policy.

Cursor's existing `agent` and `cursor` shims use the managed `cursor-agent` link.
Update the declared CLI applications through the flake pin and rebuild, rather
than their self-updaters. Credentials, histories and project dependencies are not put in the
Nix store. A development npm link such as `@liqwid-labs/lucid` belongs to its
project rather than this global application list.

On an existing installation, an unmanaged `~/.local/bin/cursor-agent` link must be
moved aside before the first activation; keep its target and user state for
rollback. A clean installation needs no Cursor vendor installer. Ubuntu copies of these tools can coexist while their package dependencies
are reviewed; Home Manager's commands take precedence in the user's shell.
Do not remove Ubuntu packages merely because the user-facing command now uses Nix.

The same module declares Chrome, LibreOffice, Krita, Transmission, Rhythmbox,
Shotwell, Dropbox, KDE Connect and KTouch. Chrome temporarily overrides the pin's
older version with the installed 155.0.8059.84 release and its checksum from
Google's signed APT index. Remove the override once the pin catches up. Existing
browser profiles, photo/music databases, office settings, torrent data, Dropbox
state and KDE Connect pairings stay in the home directory; Nix does not contain
or recreate them. `hosts/xps/application-discovery.nix` exposes the Nix desktop
entries to Rofi immediately and declares the data search path for future sessions.
It also makes KDE Connect's D-Bus activation select the Nix daemon. Dropbox's official Nix package declares the CLI and daemon
launcher; the vendor daemon still updates itself in `~/.dropbox-dist`.

`hosts/xps/jupyter.nix` declares an isolated notebook environment: JupyterLab,
Notebook, console/Qt console, widgets/LSP, OpenPyXL, Selenium, PDF tools,
SQLite-utils and HTTPX. Its Python kernel uses an absolute Nix interpreter and
ignores the old user site-packages. Its CLI wrappers leave the global Python and
Neovim provider unchanged. The module does not start a notebook server. Existing
notebooks and Jupyter settings stay in place. On an existing installation, move
an unmanaged `~/.local/share/jupyter/kernels/python3/kernel.json` aside before the
first activation; the generated kernel definition then becomes Home Manager's.
Project virtual environments remain project-owned.

Codex remains an intentional npm exception (`npm install -g @openai/codex`),
with the user-owned `~/.npm` prefix and `~/.npm/bin` session path declared on xps. The existing
Python `openai` command and its dependencies are left alone. The unused `llm` /
GPT4All application is not added to the new notebook environment. Credentials and
API keys remain outside this repository.

`hosts/xps/alacritty.nix` declares Alacritty with Home Manager's Mesa/NixGL
wrapper. Unwrapped Nix Alacritty could not create a GL configuration on this
Ubuntu X server. The wrapper supplies matching userspace graphics libraries for
this application; it keeps Intel hardware acceleration and leaves the kernel
driver, X server and global graphics environment alone. The launcher restores the original graphics environment before starting the
PTY child. This covers the default declared Fish shell and explicit `-e` /
`--command` programs, so Ubuntu applications launched inside the terminal keep
using their own compatible graphics libraries. Pre-existing caller variables
are restored exactly. The existing Alacritty TOML and X11 scaling policy remain
shared and unchanged. This terminal uses the
XPS base package pin (0.16.1 when introduced), close to the existing Ubuntu build.
The `nixgl` input follows that same `nixpkgs` input so its libraries update together.
For a future host using proprietary Nvidia drivers, choose the appropriate host
wrapper explicitly. `/usr/bin/alacritty` remains available as a local fallback
until its Ubuntu package is retired separately.

`hosts/xps/graphics.nix` selects the shared Mesa wrapper for the xps graphics
applications. `hosts/xps/picom.nix` declares the compositor and its user service.
It uses the same pinned Mesa/NixGL wrapper and established appearance settings.
i3 imports its X11 environment and starts the service idempotently, so an i3
reload cannot spawn a second compositor. VNC still forces compositor redirection
off through Picom's session-bus API and restores its previous mode on disconnect.
The service's post-start hook waits for that API and reapplies the existing
VNC display guard if Picom restarts during sharing. Backlight blanking, DPMS,
lock-screen capture and restoration remain in the existing desktop module.
`/usr/bin/picom` remains available as an Ubuntu fallback.

The following portability work remains separate:

- Validate Polybar against Ubuntu's graphics/session stack
  before replacing the working Ubuntu builds. The existing Nix i3 session still
  uses Ubuntu's fingerprint-enabled i3lock and GNOME screenshot command.
- Keep Ubuntu's hardware support, networking, authentication, SSH server and
  Docker daemon under system package management. These need a host provisioning
  layer, rather than only a Home Manager package list, for full OS recovery.
- Review the custom `/usr/local/bin/nsntrace` build and the inactive imperative
  KMonad installation separately. Declaring a keyboard daemon requires an explicit
  decision; the configured Caps/Escape behavior does not use KMonad.

## Package pins

The consolidation preserves the previously different package sets:

- `nixpkgs`: XPS base revision `3f05c8657c7016fb8cfec9ca06dac066cdeddb91`.
- `nixpkgs-darwin`: Mac base revision `0921fdb3e13e40fe25fbc52b89661a9d6d32ac68`.
- `nixpkgs-unstable`: the existing selected Linux packages.
- `nixpkgs-stable`: the existing auxiliary package set, including Fish on macOS.
- `nixgl`: Linux application graphics wrappers, following the XPS base package set.

All are pinned in the single `flake.lock`. Update a particular input intentionally
with `nix flake update INPUT`; consolidating the sources does not update packages.
The Mac's full Homebrew list is retained. Codex stays npm-managed on xps by
choice; the older custom source in `codex/` remains unused.

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
