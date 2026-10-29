"""Search the focused application's commands on X11; no global menu injection."""

import argparse
import json
import re
import subprocess
import time
from dataclasses import dataclass, field


@dataclass
class Command:
    label: str
    activate: object = field(repr=False)
    enabled: object = field(default=lambda: True, repr=False)
    identifier: object = None


def clean_label(value):
    # Menu mnemonics are not part of the command's name. Preserve escaped marks.
    value = str(value).replace("\x00", "").replace("__", "\0").replace("_", "").replace("\0", "_")
    value = value.replace("&&", "\0").replace("&", "").replace("\0", "&")
    return " ".join(value.replace("\x00", "").split())


def native_palette(wm_class):
    classes = {value.casefold() for value in wm_class}
    if classes & {"vscodium", "codium", "code", "code-oss"}:
        return ("Control_L", "Shift_L", "p")
    if "krita" in classes:
        return ("Control_L", "Return")
    # The Start Center and dialogs have no Search Commands palette.
    if any(value.startswith("libreoffice-") and value.split("-", 1)[1] in
           {"writer", "calc", "impress", "draw"} for value in classes):
        return ("Shift_L", "Escape")
    return None


def flatten_dbusmenu(layout, refresh, activate, path=(), enabled=True, depth=0):
    """Exclude disabled ancestors, separators and non-action submenu headings."""
    if depth > 16:
        return []
    item_id, props, children = layout
    if not props.get("visible", True):
        return []
    enabled = enabled and bool(props.get("enabled", True))
    if not enabled or props.get("type") == "separator":
        return []
    label = clean_label(props.get("label", ""))
    current = path + ((label,) if label else ())
    submenu = props.get("children-display") == "submenu"
    if submenu and not children:
        children = refresh(item_id)[2]
    if children or submenu or depth == 0:
        result = []
        for child in children:
            result.extend(flatten_dbusmenu(child, refresh, activate, current, enabled, depth + 1))
            if len(result) >= 2000:
                break
        return result[:2000]
    return [Command(" › ".join(current), lambda: activate(item_id), identifier=item_id)] if label else []


def choose(commands, rofi, app_name):
    # Selection is an index, not an executable string, and app labels use no markup.
    result = subprocess.run(
        [rofi, "-dmenu", "-i", "-no-custom", "-format", "i", "-p", "Commands",
         "-mesg", f"{app_name} · application menu · Esc to cancel",
         "-theme-str", 'entry { placeholder: "Find an application command…"; }'],
        input="\n".join(command.label for command in commands) + "\n",
        text=True, capture_output=True, check=False,
    )
    if result.returncode or not re.fullmatch(r"\d+\s*", result.stdout):
        return None
    index = int(result.stdout)
    return index if index < len(commands) else None


class X11:
    def __init__(self):
        from Xlib import display, X
        self.display = display.Display()
        self.X = X

    def prop(self, window, name):
        value = window.get_full_property(self.display.intern_atom(name), self.X.AnyPropertyType)
        if value is None:
            return None
        if isinstance(value.value, bytes):
            return value.value.decode("utf-8", "replace").rstrip("\0")
        return value.value

    def active(self):
        value = self.prop(self.display.screen().root, "_NET_ACTIVE_WINDOW")
        return self.display.create_resource_object("window", int(value[0])) if value is not None and len(value) and value[0] else None

    def is_focused(self, window):
        active = self.active()
        return active is not None and active.id == window.id

    def send_palette(self, window, keys):
        from Xlib import XK
        from Xlib.ext import xtest
        # Wait for the global shortcut's physical modifiers to be released. Never
        # clear held user modifiers or send a command to a newly focused window.
        modifiers = {code for group in self.display.get_modifier_mapping() for code in group if code}
        deadline = time.monotonic() + 2
        while True:
            keymap = self.display.query_keymap()
            if not any(keymap[code // 8] & (1 << (code % 8)) for code in modifiers):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Release the modifier keys and try again.")
            time.sleep(0.02)
        if not self.is_focused(window):
            raise RuntimeError("Focus changed; no shortcut was sent. Try again in the application.")
        codes = [self.display.keysym_to_keycode(XK.string_to_keysym(key)) for key in keys]
        if not all(codes):
            raise RuntimeError("This keyboard layout cannot send the application's palette shortcut.")
        pressed = []
        try:
            for code in codes:
                xtest.fake_input(self.display, self.X.KeyPress, code)
                pressed.append(code)
            self.display.sync()
        finally:
            for code in reversed(pressed):
                xtest.fake_input(self.display, self.X.KeyRelease, code)
            self.display.sync()


def pump(seconds=0.25):
    from gi.repository import GLib
    deadline = time.monotonic() + seconds
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        time.sleep(0.01)


def gtk_commands(bus, x11, window):
    from gi.repository import Gio
    owner = x11.prop(window, "_GTK_UNIQUE_BUS_NAME")
    menu_path = x11.prop(window, "_GTK_MENUBAR_OBJECT_PATH") or x11.prop(window, "_GTK_APP_MENU_OBJECT_PATH")
    if not owner or not menu_path:
        return []
    paths = {prefix: x11.prop(window, name) for prefix, name in (
        ("app", "_GTK_APPLICATION_OBJECT_PATH"), ("win", "_GTK_WINDOW_OBJECT_PATH"),
        ("unity", "_UNITY_OBJECT_PATH"))}
    actions = {prefix: Gio.DBusActionGroup.get(bus, owner, path) for prefix, path in paths.items() if path}
    model = Gio.DBusMenuModel.get(bus, owner, menu_path)
    # These proxies subscribe lazily, on first access rather than construction.
    model.get_n_items()
    for group in actions.values():
        group.list_actions()
    result = []
    # Accessing each linked model subscribes it. Retain models while the menu is
    # open so GIO keeps subscriptions and action state current.
    retained = [model]
    def visit(current, path=(), ancestors=(), depth=0):
        if depth > 16 or len(result) >= 2000 or id(current) in ancestors:
            return
        retained.append(current)
        current.get_n_items()
        pump(0.12)
        for index in range(current.get_n_items()):
            text = current.get_item_attribute_value(index, "label", None)
            label = clean_label(text.unpack()) if text else ""
            next_path = path + ((label,) if label else ())
            for kind in ("section", "submenu"):
                linked = current.get_item_link(index, kind)
                if linked is not None:
                    visit(linked, next_path, ancestors + (id(current),), depth + 1)
            action = current.get_item_attribute_value(index, "action", None)
            if action is None or not label:
                continue
            full_name = action.unpack()
            prefix, separator, name = full_name.partition(".")
            group = actions.get(prefix) if separator else None
            if group is None or not group.has_action(name) or not group.get_action_enabled(name):
                continue
            target = current.get_item_attribute_value(index, "target", None)
            result.append(Command(" › ".join(next_path),
                                  lambda g=group, n=name, t=target: g.activate_action(n, t),
                                  lambda g=group, n=name: g.has_action(n) and g.get_action_enabled(n)))
    pump()
    visit(model)
    return result


def dbusmenu_commands(bus, x11, window):
    from gi.repository import Gio, GLib
    owner = x11.prop(window, "_KDE_NET_WM_APPMENU_SERVICE_NAME")
    path = x11.prop(window, "_KDE_NET_WM_APPMENU_OBJECT_PATH")
    if not owner or not path:
        try:
            value = bus.call_sync("com.canonical.AppMenu.Registrar", "/com/canonical/AppMenu/Registrar",
                                  "com.canonical.AppMenu.Registrar", "GetMenuForWindow",
                                  GLib.Variant("(u)", (window.id,)), None,
                                  Gio.DBusCallFlags.NO_AUTO_START, 1000, None)
            owner, path = value.unpack()
        except GLib.Error:
            return []
    if not owner or not path or path == "/":
        return []
    # Pin the unique connection so a well-known name changing owners cannot
    # redirect an already displayed command to a different application.
    owner = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                          "org.freedesktop.DBus", "GetNameOwner", GLib.Variant("(s)", (owner,)),
                          None, Gio.DBusCallFlags.NO_AUTO_START, 1000, None).unpack()[0]
    def call(method, arguments):
        return bus.call_sync(owner, path, "com.canonical.dbusmenu", method, arguments,
                             None, Gio.DBusCallFlags.NO_AUTO_START, 1500, None).unpack()
    def layout(item_id):
        call("AboutToShow", GLib.Variant("(i)", (item_id,)))
        return call("GetLayout", GLib.Variant("(iias)", (item_id, -1,
                    ["label", "enabled", "visible", "type", "children-display"])))[1]
    def activate(item_id):
        call("Event", GLib.Variant("(isvu)", (item_id, "clicked", GLib.Variant("i", 0), 0)))
    commands = flatten_dbusmenu(layout(0), layout, activate)
    # Re-read enabled state after the user has searched, without executing it.
    for command in commands:
        command.enabled = lambda c=command: c.identifier in {item.identifier for item in flatten_dbusmenu(layout(0), layout, activate)}
    return commands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rofi", required=True)
    parser.add_argument("--inspect", action="store_true", help="Report current backend without sending input or running a command")
    args = parser.parse_args()
    from gi.repository import Gio, GLib
    from Xlib import error
    try:
        x11 = X11()
        window = x11.active()
        if window is None:
            raise RuntimeError("Focus an application window first.")
        wm_class = window.get_wm_class() or ()
        app_name = wm_class[-1] if wm_class else "This application"
        keys = native_palette(wm_class)
        if keys:
            if args.inspect:
                print(json.dumps({"app": app_name, "backend": "native", "keys": keys}))
            else:
                x11.send_palette(window, keys)
            return 0
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        commands = gtk_commands(bus, x11, window) or dbusmenu_commands(bus, x11, window)
        if args.inspect:
            print(json.dumps({"app": app_name, "backend": "menu" if commands else "unsupported",
                              "commands": [command.label for command in commands]}))
            return 0
        if not commands:
            raise RuntimeError(f"{app_name} does not expose a searchable application menu.\n"
                               "Use its own menus or shortcuts.")
        index = choose(commands, args.rofi, app_name)
        if index is not None:
            # Let the WM restore focus after Rofi exits, and process queued GIO
            # action-state changes before checking whether the result is enabled.
            deadline = time.monotonic() + 0.3
            while not x11.is_focused(window) and time.monotonic() < deadline:
                pump(0.02)
            pump(0.03)
            if not x11.is_focused(window):
                raise RuntimeError("Focus changed; no command was run. Try again in the application.")
            if not commands[index].enabled():
                raise RuntimeError("That command is no longer available. Open command search again.")
            commands[index].activate()
            bus.flush_sync(None)
        return 0
    except (RuntimeError, GLib.Error, error.XError, OSError) as exc:
        message = str(exc)
        if args.inspect:
            print(json.dumps({"backend": "error", "message": message}))
            return 1
        subprocess.run([args.rofi, "-e", GLib.markup_escape_text(message)], check=False)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
