# Zen on xps

Zen's Linux beta package is installed through Home Manager, using the pinned
`zen-browser` input and the existing unstable nixpkgs input. The community flake
packages the official Zen release. The generic-Linux NixGL wrapper supplies the
host graphics integration. Package updates happen through the flake; in-app
binary updates are disabled. Tridactyl's native helper is included.

Launch **Zen Browser** from Rofi, or run `zen-beta`. Firefox remains available.

## Browser data

The browser profile is mutable private state under `~/.zen/`. It is deliberately
outside Home Manager's generated files and the Nix store. Back it up through the
normal home-directory backup, with Zen closed for a consistent copy.

The initial profile was copied once from mbp's Zen 1.23.4b profile on 2026-10-27.
The import preserves installed extensions and their storage, bookmarks, history,
cookies, saved-password databases, containers, Zen customizations, workspaces
and session files. macOS native media plugins and generated startup/installation
caches are regenerated for Linux. Extension registry paths are adjusted for the
new profile location; browser data is never embedded in this repository.

No synchronization job is configured. Later changes on the two machines are
independent. Some website sessions or OS-specific extension integrations may
require signing in or unlocking again on Linux.

## Imported local documents

On 2026-10-28, 84 documents referenced by the imported tabs were copied to
`~/Downloads/Zen-imported-documents/mbp-home/`, preserving their original relative
folder structure. Saved tab and navigation links, including PDF page fragments,
now use these Linux copies. One other document was already missing on mbp;
its original link remains in the session. Later edits to the Mac and Linux
copies are independent.

Restore this Downloads directory together with `~/.zen/` to keep those tabs
usable. It is covered by the current home-directory backup policy. History
records retain their original Mac URLs; the saved session uses the Linux paths.

## Recovery

Build and activate the normal `homeConfigurations.xps.activationPackage` to
restore the application. Restore `~/.zen/` from a closed-browser backup to
recover the profile; verify its owner and keep the profile root mode `0700`.
If necessary, use `zen-beta --ProfileManager` to select a restored profile.
Do not launch a profile with an older Zen release than the one that last wrote
it. Never place cookies, password files or extension storage in Nix source files.

Migration follows [Zen's profile-copy guide](https://docs.zen-browser.app/guides/manage-profiles).
The [community package source](https://github.com/0xc000022070/zen-browser-flake)
is pinned in `flake.lock`.
