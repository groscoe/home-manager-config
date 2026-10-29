# Linux hardware profiles

`hardware-profiles/xps.nix` is the physical xps inventory. It is data, separate
from the reusable option schema in `hardware-profile/default.nix` and the Linux
application/session modules. It declares the internal display, wireless
interface, battery/AC supplies, backlight, internal NVMe controllers, NixGL
wrapper, DPI,
integer toolkit scale, cursor size, keyboard/remaps, local tmux prefix and tablet
policy. The existing xps values and behavior are preserved.

The selected values feed the actual Polybar configuration, X resources,
xsettingsd, cursor and notification scaling, keyboard/tablet startup, shortcut
reference, health monitoring, VNC panel selection and brightness installer.
The VNC helper matches the configured output exactly rather than selecting any
output whose name starts with eDP. The brightness installer accepts only one
validated backlight basename; its existing xps udev rule is unchanged.

## A different machine

Inspect identifiers without changing devices:

```sh
xrandr --query
ls /sys/class/power_supply /sys/class/backlight /sys/class/net /sys/class/nvme
```

Copy the physical inventory to a new file and explicitly import it as
`personal.hardware` in that host's extra module. The physical defaults use
`mkDefault`, so an explicit profile replaces them. Use null for absent battery,
AC, Wi-Fi or backlight devices, and an empty NVMe list when none is supported.
Battery and AC must be declared together. With no battery/NVMe, health tracking
is disabled; no absent battery/Wi-Fi module is emitted in the bar. With no
supported backlight/display pair, this LCD-specific VNC server is disabled.
SSH and the ordinary graphical session remain available.

Review DPI, integer scale and cursor size together. The xps uses 192/2/48; the
VM uses 96/1/24. Use the local tmux prefix `ç` for the original ABNT-2 policy or
`;` for a keyboard without that key. The original per-client SSH/local behavior
is retained for xps; the semicolon profile uses that prefix in both contexts.
The shortcut footer receives the selected prefix. Re-enroll device secrets and
reinstall any required OS drivers/permissions separately; a profile cannot
reproduce firmware, fingerprint enrollment or disk contents.

## Virtual-machine profile

`homeConfigurations.xps-vm` uses `hardware-profiles/qemu.nix`: Virtual-1, normal
DPI, US keyboard and semicolon prefix, without a physical battery, Wi-Fi,
backlight or NVMe controller. Production Restic backups and scheduled antivirus
scans are disabled in this disposable-guest profile. It uses the same pinned
applications and user configuration as xps.

```sh
nix build --no-write-lock-file .#homeConfigurations.xps-vm.activationPackage
```

Activate that result only inside the intended guest. Check the actual guest's
XRandR output and adjust its descriptor if it differs. The profile builds and
configuration contracts do not boot a VM, install a display manager or prove
that a particular graphics driver works.

## Validation

`checks.x86_64-linux.hardware-profiles` reads the generated physical and virtual
bar/startup settings, checks optional device/service omission and exercises the
virtual prefix in an isolated tmux server. It also uses Xvfb to test exact gamma
save/blank/restore on a non-eDP output and refusal of an absent output. Existing
backlight permission tests cover alternate device names and injection/path
rejection. `vm-home-profile` builds the complete guest profile. These checks
use temporary homes, sockets and X displays, with no real secrets or hardware.

The Ubuntu companion, encrypted mounts, backup exports and network/firewall
policies still have OS/site-specific requirements. This change parameterizes
the user configuration; it does not establish support for another distribution.
