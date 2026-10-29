# Lake Bled on xps

The xps host imports this module; mbp's appearance and terminal configuration
are unaffected. `palette.json` supplies the shared colours for i3 focus borders,
Polybar, Rofi, Alacritty, Dunst and the shortcut reference. Alacritty retains its
Source Code Pro size, scrollback, NixGL wrapper and clean child environment.
The existing 192 DPI, cursor and toolkit scaling settings are retained.
The tmux status line and pane/selection colours match the terminal; the existing
per-client prefixes, clipboard bindings, plugins and hooks are preserved.

The photograph is the original **4770 × 3177** JPEG, with SHA256
`18a19c0430b95d5ffdb1e50fb509ff5485fd26de416de4ab2322da7126cc4039`.
Feh fills the 3840 × 2400 display with a small vertical crop and no upscaling.
The original is linked at `~/Pictures/Wallpapers/lake-bled-sunrise.jpg`.
It is not recoloured, blurred or edited.

## Photograph attribution

**Lake Bled sunrise (2)**, photograph by **Bas Lammers**, 30 July 2009.
Licensed under **Creative Commons Attribution 2.0 Generic**.

- Source and original: https://commons.wikimedia.org/wiki/File:Lake_Bled_sunrise_(2).jpg
- Licence: https://creativecommons.org/licenses/by/2.0/

Retain this attribution and licence when redistributing the photograph. The
photograph's licence applies to the JPEG independently of the configuration.

## Use

- Open **Keyboard shortcuts** from Super+Space, click **Keys** in Polybar, or run
  `xps-shortcuts`. **Desktop**, **tmux**, **Copy mode** and **Advanced** tabs group
  window controls, terminal sessions, vi selections, resize/gap controls and
  clipboard variants. Typing in search always searches all four tabs; the result
  headings identify the category. Clicking a tab clears search and shows that tab.
  The keyboard selector labels Super as Command and Alt as Option for XPS Desktop
  on Mac; it does not change keyboard mappings.
- The reference reads the managed i3 file and the running tmux server's prefix
  and vi copy-mode tables. It omits absent or reassigned tmux actions. If tmux is
  stopped, a labelled fallback shows this configuration's managed defaults.
  It never starts a tmux server or executes a referenced action. Resize-mode
  keys stay in **Advanced**, with their mode context shown explicitly.
- `xps-shortcuts --list` prints the current reference without opening a window.
  `--category 'Copy mode'` narrows an unfiltered listing; `--search clipboard`
  searches every category. `--keyboard mac` uses Mac/VNC modifier labels.
- Package builds check the GTK runtime and run the tab, global-search, modifier
  and column-layout interactions on an isolated Xvfb display with synthetic tmux
  tables. These checks do not access a live desktop or tmux server.
- **Notices** in Polybar recalls the previous notification; right-click toggles
  notification pausing. Critical Dunst notifications wait for dismissal.
- **Wi-Fi** opens the existing Rofi network menu; Bluetooth remains available
  through the launcher. Both use the shared Rofi theme.
- **Super+Shift+/** opens application command search (**Command+Shift+/** in
  XPS Desktop). It uses native palettes for LibreOffice, Krita and VSCodium,
  or the themed Rofi search when another app exports a compatible menu.
  See [supported backends and limitations](../command-search/README.md).
- The power icon opens the shared-theme session menu. Lock is immediate;
  suspend, logout, restart and shutdown require a separate confirmation with
  **Cancel** selected by default. Opening the menu performs no power action.

## Activation and VNC

Build and activate the normal `homeConfigurations.xps.activationPackage`.
During a graphical activation the module reloads i3, applies the wallpaper and
restarts Polybar and Dunst. Existing Alacritty windows reload the colour file.
No logout is required. A text-only activation applies the display settings at
the next i3 login. A previous Home Manager generation remains a rollback route.

`xps-desktop/server.py`, its systemd service, `hosts/xps/picom.nix` and the Picom
configuration are unchanged. This theme adds no compositor blur, fading,
transparency or animations. The existing VNC bypass keeps Picom running while
unredirecting rendering. The panel gamma/backlight and DPMS restoration logic
remain in the existing sharing module. Activation refreshes that logic when
sharing is active, after reloading the desktop.

The bar and scaling use the selected [hardware profile](../../../hardware-profile/README.md).
`hardware-profiles/xps.nix` preserves the current display, Wi-Fi, battery and AC
identifiers; the VM profile omits unavailable device modules. This module does not theme SDDM or i3lock, or
modify their fingerprint/password policies.
