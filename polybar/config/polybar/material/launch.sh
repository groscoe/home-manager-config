#!/usr/bin/env bash
# Keep the existing theme entry point; systemd owns the single bar instance.
exec "$HOME/.nix-profile/bin/xps-start-polybar"
