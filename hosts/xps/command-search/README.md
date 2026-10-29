# Application command search

`Super+Shift+/` searches commands in the focused application. In XPS Desktop,
use `Command+Shift+/`, like macOS menu search. The binding uses the slash symbol
rather than a fixed physical keycode, so it follows the ABNT-2 and Mac layouts.
The shortcut is triggered on release, and native dispatch waits for held
modifiers to clear before sending input to the same focused window.

- LibreOffice Writer/Calc/Impress/Draw: native Search Commands (`Shift+Esc`).
- Krita: native Search Actions (`Ctrl+Enter`).
- VSCodium / VS Code: native command palette (`Ctrl+Shift+P`).
- Other applications: a Lake Bled Rofi search of their exported GMenu or
  D-Bus menus, when available. Menu paths disambiguate similarly named commands;
  disabled, invisible and separator items are omitted. Escape cancels.
- Unsupported applications receive an explanation. Standard Linux Firefox and
  Alacritty do not expose a compatible application menu.

This module neither enables global GTK menu injection nor replaces application
menu bars. Some applications do not export menus, so support is intentionally
conditional. Existing Qt window menu properties and an existing AppMenu
registrar are supported; no registrar or exporter is started by this module.
This avoids globally affecting Electron applications. The native palettes keep
their application's own appearance; the fallback inherits the shared Rofi theme.

`xps-command-search --inspect` reports the backend and available menu labels
without sending keystrokes or executing a command. Command labels are display
data, never shell commands. Selecting a result activates its application action
through D-Bus. Focus changes abort dispatch, and GMenu targets retain their
original variant types and action namespaces.

No VNC, compositor, display-power, lock, clipboard or tmux settings are changed.

## References and verification

- [LibreOffice Search Commands](https://help.libreoffice.org/latest/en-US/text/shared/01/search_commands.html)
- [Krita Search Actions](https://docs.krita.org/en/reference_manual/preferences/shortcut_settings.html)
- [VS Code keybindings](https://code.visualstudio.com/docs/reference/default-keybindings)
- [Rofi desktop menu-search background](https://github.com/giomatfois62/rofi-desktop#global-menu)
- [Electron global-menu regression](https://github.com/microsoft/vscode/issues/334058)

Package builds run `test-runtime.py` on an isolated Xvfb display and private
D-Bus session. It exports actual GMenu/action and Qt-style D-Bus menu fixtures,
checks typed action targets, disabled actions and namespaces, verifies native
keyboard input and confirms that changed focus aborts dispatch. Unit tests in
`../tests/test_command_search.py` also cover cancellation, selection validation,
mnemonic handling, lazy submenus and disabled ancestors. Tests do not touch the
live desktop or the user's application data.
