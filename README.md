# Home Manager Config

Declarative user and system configuration for:

- macOS (`aarch64-darwin`) via `nix-darwin` + Home Manager
- Linux (`x86_64-linux`) via Home Manager

## Flake Targets

- macOS system: `.#darwinConfigurations.groscoe-macos`
- Linux home config: `.#homeConfigurations.groscoe`

## Prerequisites

- Nix with flakes enabled (`nix-command` + `flakes`)
- `git`

Clone:

```bash
git clone <your-fork-or-repo-url>
cd home-manager-config
```

## macOS

### First Install (bootstrap)

```bash
sudo -H nix run github:LnL7/nix-darwin/nix-darwin-25.11#darwin-rebuild -- \
  switch --flake /Users/groscoe/Projects/home-manager-config#groscoe-macos
```

After first activation, use the installed binary for future updates.

### Update / Re-apply

```bash
sudo -H /run/current-system/sw/bin/darwin-rebuild switch \
  --flake /Users/groscoe/Projects/home-manager-config#groscoe-macos
```

## Linux

### Install / Update

This works whether or not the `home-manager` CLI is already installed:

```bash
nix build .#homeConfigurations.groscoe.activationPackage
./result/activate
```

Alternative (if `home-manager` is installed):

```bash
home-manager switch --flake .#groscoe
```

## Typical Update Workflow

```bash
git pull
```

Then run platform apply command:

- macOS: `darwin-rebuild switch --flake ...#groscoe-macos`
- Linux: `nix build .#homeConfigurations.groscoe.activationPackage && ./result/activate`

## Notes

- Homebrew packages on macOS are managed declaratively via `homebrew.*` in `flake.nix`.
- Linux remains unaffected by macOS-only `darwinConfigurations` settings.
