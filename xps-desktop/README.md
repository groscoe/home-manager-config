# XPS Desktop

This shared Home Manager module runs TigerVNC 1.16 on Linux and installs a Mac
launcher for the existing i3 desktop. Import `./xps-desktop` and enable
`services.xps-desktop.enable` in both configurations. No flake input is needed.

## Connect

Open `~/Applications/XPS Desktop.app`, or run `xps-desktop` on mbp. At the first
Screen Sharing connection, enter the VNC password chosen on xps. Screen Sharing
can remember that password if you select its checkbox. Select View → Turn Scaling
On to fit the laptop's desktop into the viewer; fullscreen uses a macOS Space.
Control mode must be enabled in the viewer's toolbar. Command acts as i3's Super
key over VNC, so Command+Enter opens a terminal. Physical XPS key mappings are
unchanged. Option acts as Alt.

The default SSH destination is `192.168.1.2:2222`. Away from home, use
`xps-desktop --host 100.97.96.61`. SSH host-key checking and the user's SSH identity
configuration are retained. Agent and X11 forwarding are disabled only for these
desktop connections, without changing global SSH preferences.

The launcher starts the user service, creates an SSH tunnel to its private Unix
socket, and opens macOS Screen Sharing. Closing the last viewer closes the tunnel
after about 30 seconds. `xps-desktop --disconnect` closes it immediately;
`xps-desktop --status` reports its state. The server exits after five minutes with
no connected viewers and starts again on the next launch.

## Linux service and credentials

An existing local i3 login is required. VNC shares that same session and its lock
screen; it does not bypass the screen lock or create a separate desktop. Enter
the normal Linux login password to unlock remotely; the fingerprint reader still
requires a physical touch. BIOS, early volume unlock and the SDDM login screen are
outside this user-session service.

`xps-desktop-control password` creates or changes the user-private password file
at `~/.local/state/xps-desktop/passwd`. VNC passwords use the first eight
characters, so choose a unique eight-character password. Passwords are never put
in Nix sources, the Nix store, command arguments or launcher logs.

The server has no TCP listener. Its only endpoint is
`/run/user/1000/xps-desktop/desktop.sock`, mode 0600 inside a 0700 runtime directory.
The service is additionally limited to Unix sockets by systemd. The Mac exposes
only an authenticated VNC listener on `127.0.0.1:59320` while its SSH tunnel runs.
No UFW, Tailscale, PAM, root service or firmware change is required.

The XPS graphics driver becomes very slow when DPMS powers down the display.
During sharing the service keeps rendering active, sets the built-in hardware
backlight to zero and blanks the panel's hardware colour lookup table. VNC still
sees the normal framebuffer. The backlight is off while the graphics pipeline
remains awake. The exact original brightness, colour table and display-power
state are restored when the service stops, including on failure. A deliberate
brightness-key change during sharing takes precedence over the saved brightness.
Automatic screen locking remains enabled. Stop sharing before physical use.

On xps, run `install-xps-backlight-access` once to authorize that brightness
control. It prompts for sudo, verifies your primary group contains only your
account, and installs a narrow udev rule granting that group write access only
to `/sys/class/backlight/intel_backlight/brightness`. This remains available for
restoration after logout, unlike logind's foreground-session-only API. It adds
no group memberships, root daemon, sudo exception or general device access.
The installer saves permission metadata and prints a rollback command; it does
not change brightness itself. Its source is `install-backlight-access.py`.

After closing the last viewer, the Mac closes its tunnel after about 30 seconds
and stops the remote service only if no other viewers remain. The five-minute
server idle timeout is the fallback if the Mac or network disappears. Use
`xps-desktop --disconnect` for immediate disconnection, or
`xps-desktop-control stop` on xps to restore its physical display directly.

Display resizing is disabled on the server so remote clients cannot change the
laptop's resolution or HiDPI settings. Clipboard forwarding uses CLIPBOARD only;
selecting text alone does not overwrite the other machine's clipboard. Server
pixel comparison is always enabled to avoid retransmitting unchanged areas.
While sharing, the service uses Picom's session-bus API to unredirect the desktop,
disabling compositor effects that substantially slow remote redraws. Picom stays
running. Its original mode is restored on service stop; manual mode changes or a
new Picom process take precedence. The managed Picom configuration enables this
per-user D-Bus interface. No system-bus access or new network listener is added.
The accompanying Picom configuration enables fullscreen unredirection so i3lock
is captured correctly; otherwise the compositor can leave the desktop visible
behind the active lock. Authentication and automatic locking remain enabled.

Inspect `systemctl --user status xps-desktop.service` and
`journalctl --user -u xps-desktop.service` on xps for server diagnostics. Mac
connection diagnostics are private files in `~/Library/Caches/xps-desktop/`.
