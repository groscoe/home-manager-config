# KDE Connect on xps

Home Manager owns the pinned KDE Connect package, supervised daemon, D-Bus
activation, autostart override, login hook and Rofi device menu. Pairing keys,
certificates, plugin preferences and received files remain mutable user data;
none are copied into Git or the Nix store.

## Everyday use

Press **Super+Space**, search **KDE Connect devices**, and press Enter. Or run
`rofi-kdeconnect` from a graphical terminal. The menu lists known devices and
connection status. Select a connected device to ping it, ring it, send the
clipboard, share a file, or share text/a URL. Pairing requests and the full KDE
Connect settings application are also available. Refresh rediscovers devices;
Restart restarts only this daemon. Escape cancels without sending anything.
A ping/ring/share is sent only when explicitly selected. Device IDs and text
are passed as literal arguments, never evaluated by a shell. KDE Connect's
normal pairing and TLS trust still apply.

The upstream CLI waits about two seconds for discovery when listing devices;
the first menu can take that long to appear. "Not connected" includes both
paired devices currently offline and discoverable devices not yet paired.

## Startup and recovery

`kdeconnect.service` is enabled in the user's `default.target` with automatic
restart and D-Bus name ownership. On xps, **user lingering is already enabled**,
so it can start at boot without a graphical login. An offscreen Qt backend
keeps network features available before X11 exists. At GUI login,
`xps-apply-hidpi` imports DISPLAY/XAUTHORITY and invokes `session.py` to replace
a headless instance with an X11 instance for desktop/clipboard integration.
Repeated session hooks do not restart an existing X11 daemon.

The per-user hidden XDG autostart entry suppresses Ubuntu's independent daemon.
The user D-Bus activation file points at the same systemd service and package.
Neither an extra tray indicator nor Plasma is required.

Useful checks:

```sh
systemctl --user status kdeconnect.service
systemctl --user is-enabled kdeconnect.service
loginctl show-user "$USER" -p Linger
journalctl --user -u kdeconnect.service --since today
kdeconnect-cli --list-devices
```

On a new machine, boot-before-login requires `sudo loginctl enable-linger USER`
in addition to Home Manager activation. Without lingering it starts when the
user manager starts at login. The host must be powered on, not suspended, and
have networking available. X11 clipboard/UI functions require a GUI session.
No successful reboot test is claimed for this change: boot conditions were
simulated by removing DISPLAY/XAUTHORITY from the user manager, restarting the
service, then restoring the real session; both transitions passed.

## LAN and the existing two-tailnet installation

KDE Connect uses TCP/UDP 1714–1764. The one-time protected change on xps added:

- UFW allowances from 192.168.1.0/24 on wlp0s20f3 for those two protocols.
- The matching dynamically scoped home-LAN IPv6 rules in xps-host-firewall.
- TCP/UDP range exceptions in XPS-PERSONAL4/6 for the existing personal
  Tailscale userspace daemon's loopback forwarding path.

Other firewall policies, both tailnet identities and daemon configurations
were preserved. The work tailnet's existing policy was not broadened. These
root-owned firewall rules are **not automatically applied by Home Manager**.
`network-access.py` records the reviewed, one-time Ubuntu/xps migration. It
requires an exact original firewall hash and refuses an unfamiliar baseline;
it is not a generic firewall manager. Run its read-only preflight before
considering `sudo python3 -I .../network-access.py --apply`. It prints a
root-owned backup/rollback path and restores that backup on apply failure.
An already-migrated machine should not rerun it.

The live backup from the 2026-11-10 installation is
`/var/backups/xps-kdeconnect-y8xfqqct`; rollback is
`sudo /bin/bash /var/backups/xps-kdeconnect-y8xfqqct/rollback.sh`.

Broadcast discovery does not cross Tailscale. Clients that support explicit
peer addresses can be configured with xps's personal-tailnet address
(currently 100.97.96.61). The unusual personal userspace installation also
means xps does not have a normal personal-tailnet network interface for
outgoing discovery. Do not route personal peer addresses through the work
interface or change tailnet settings to work around this without review.

Verified from mbp: TCP 1716 reachable over both LAN and personal Tailscale.
Verified application connections: Soduto on mbp and KDE Connect on S24 over
LAN. **Soduto discovery/application connectivity away from the LAN has not
been verified or configured**; the user explicitly deferred a Mac helper.
A reachable tailnet port alone does not demonstrate file-transfer/clipboard
interoperability over that path.

## Validation

- Complete xps Home Manager profile built and activated.
- Menu input/error/cancellation tests are included in personal-scripts checks.
- Live daemon crash/restart, headless startup, X11 transition and repeat-hook
  tests passed; original pairing identity/certificate/private key retained.
- Menu visually checked in an isolated Xvfb display with the installed theme
  while the physical session remained locked.
- Isolated firewall namespace tests checked actual TCP/UDP responses at range
  edges and neighboring ports, LAN/work/personal/outside policies, IPv6,
  UFW reload, concurrent refresh and revocation when leaving the home LAN.
- No clipboard contents, personal files or ring requests were sent as tests.
