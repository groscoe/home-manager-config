"""Isolated real X11/GIO integration test, run under Xvfb and a private bus."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from gi.repository import Gio, GLib
from Xlib import X, Xatom, XK, display

args = argparse.ArgumentParser()
args.add_argument("--script", required=True)
opts = args.parse_args()
spec = importlib.util.spec_from_file_location("runtime_command_search", opts.script)
search = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = search
spec.loader.exec_module(search)
d = display.Display()
window = d.screen().root.create_window(0, 0, 200, 200, 0, d.screen().root_depth,
                                      event_mask=X.KeyPressMask | X.KeyReleaseMask)
window.set_wm_class("fixture", "MenuFixture")
window.map()
window.set_input_focus(X.RevertToParent, X.CurrentTime)
d.screen().root.change_property(d.intern_atom("_NET_ACTIVE_WINDOW"), Xatom.WINDOW, 32, [window.id])
d.sync()
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
def prop(name, value):
    window.change_property(d.intern_atom(name), d.intern_atom("UTF8_STRING"), 8, value.encode())
    d.sync()
def run(*extra):
    process = subprocess.Popen([sys.executable, "-I", opts.script, "--rofi", rofi, *extra], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 12
    while process.poll() is None and time.monotonic() < deadline:
        search.pump(0.01)
    if process.poll() is None:
        process.kill()
        raise AssertionError("Search subprocess timed out")
    stdout, stderr = process.communicate()
    assert process.returncode == 0, (stdout, stderr)
    return stdout

with tempfile.TemporaryDirectory() as tmp:
    # This test double selects index zero. The actual Rofi UI is checked live.
    rofi = str(Path(tmp) / "rofi")
    Path(rofi).write_text(f"#!{sys.executable}\nimport sys\nsys.stdin.read()\nprint('0')\n")
    Path(rofi).chmod(0o755)
    received = []
    group = Gio.SimpleActionGroup()
    action = Gio.SimpleAction.new("amount", GLib.VariantType.new("i"))
    action.connect("activate", lambda a, value: received.append((value.get_type_string(), value.unpack())))
    disabled = Gio.SimpleAction.new("disabled", None)
    disabled.set_enabled(False)
    group.add_action(action)
    group.add_action(disabled)
    sub = Gio.Menu()
    item = Gio.MenuItem.new("_Set amount", None)
    item.set_action_and_target_value("app.amount", GLib.Variant("i", 42))
    sub.append_item(item)
    sub.append("Disabled command", "app.disabled")
    sub.append("Wrong namespace", "win.amount")
    menu = Gio.Menu()
    menu.append_submenu("_File", sub)
    menu_id = bus.export_menu_model("/fixture/menu", menu)
    action_id = bus.export_action_group("/fixture/app", group)
    prop("_GTK_UNIQUE_BUS_NAME", bus.get_unique_name())
    prop("_GTK_MENUBAR_OBJECT_PATH", "/fixture/menu")
    prop("_GTK_APPLICATION_OBJECT_PATH", "/fixture/app")
    report = json.loads(run("--inspect"))
    assert report['commands'] == ['File › Set amount'], report
    assert not received
    run()
    search.pump(0.05)
    assert received == [("i", 42)], received
    bus.unexport_menu_model(menu_id)
    bus.unexport_action_group(action_id)
    for name in ("_GTK_UNIQUE_BUS_NAME", "_GTK_MENUBAR_OBJECT_PATH", "_GTK_APPLICATION_OBJECT_PATH"):
        window.delete_property(d.intern_atom(name))
    # The direct Qt D-Bus-menu path is exercised against an actual exported API.
    received.clear()
    xml = '''<node><interface name="com.canonical.dbusmenu">
    <method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
    <method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/>
    <arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
    <method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/></method>
    </interface></node>'''
    child = GLib.Variant("(ia{sv}av)", (7, {"label": GLib.Variant("s", "_About fixture")}, []))
    def method(connection, sender, path, iface, name, params, invocation):
        if name == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        elif name == "GetLayout":
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (1, (0, {}, [child]))))
        else:
            received.append(params.unpack()[:2])
            invocation.return_value(None)
    registration = bus.register_object("/fixture/dbusmenu", Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0], method, None, None)
    prop("_KDE_NET_WM_APPMENU_SERVICE_NAME", bus.get_unique_name())
    prop("_KDE_NET_WM_APPMENU_OBJECT_PATH", "/fixture/dbusmenu")
    assert "About fixture" in run("--inspect")
    assert not received
    run()
    assert received == [(7, "clicked")], received
    bus.unregister_object(registration)
    # Native input must deliver the expected chord to the focused test window.
    window.set_wm_class("krita", "krita")
    d.sync()
    run()
    d.sync()
    pressed = []
    while d.pending_events():
        event = d.next_event()
        if event.type == X.KeyPress:
            pressed.append(d.keycode_to_keysym(event.detail, 0))
    assert pressed == [XK.string_to_keysym("Control_L"), XK.string_to_keysym("Return")], pressed
    # A focus change must abort before sending input.
    d.screen().root.change_property(d.intern_atom("_NET_ACTIVE_WINDOW"), Xatom.WINDOW, 32, [0])
    d.sync()
    try:
        search.X11().send_palette(window, ("Return",))
    except RuntimeError:
        pass
    else:
        raise AssertionError("Focus-change guard failed")

print("Command-search integration passed: GMenu target types/namespaces, D-Bus menus, native XTest input and focus guard")
