"""Dispatch, menu filtering and selection must not treat labels as shell code."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("command_search", Path(__file__).resolve().parents[1] / "command-search/search.py")
search = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = search
spec.loader.exec_module(search)


class CommandSearchTests(unittest.TestCase):
    def test_native_palettes_and_unsupported_classes(self):
        self.assertEqual(search.native_palette(("libreoffice", "libreoffice-writer")), ("Shift_L", "Escape"))
        self.assertEqual(search.native_palette(("krita", "krita")), ("Control_L", "Return"))
        self.assertEqual(search.native_palette(("codium", "VSCodium")), ("Control_L", "Shift_L", "p"))
        for value in ("libreoffice-startcenter", "firefox", "Alacritty", "not-vscodium"):
            self.assertIsNone(search.native_palette((value,)))

    def test_labels_preserve_escaped_mnemonics_and_cannot_inject_rofi_rows(self):
        self.assertEqual(search.clean_label("_Save && _Close\n now"), "Save & Close now")
        self.assertEqual(search.clean_label("foo__bar"), "foo_bar")
        self.assertEqual(search.clean_label("x\x00icon\x1fy"), "xicon y")

    def test_dbusmenu_omits_disabled_parents_invisible_and_separators(self):
        root = (0, {}, [(1, {"label": "_File"}, [
            (2, {"label": "Open"}, []),
            (3, {"label": "Hidden", "visible": False}, []),
            (4, {"label": "--", "type": "separator"}, []),
            (5, {"label": "Disabled", "enabled": False}, [(6, {"label": "Child"}, [])]),
        ])])
        activated = []
        commands = search.flatten_dbusmenu(root, None, activated.append)
        self.assertEqual([command.label for command in commands], ["File › Open"])
        self.assertEqual(activated, [])
        commands[0].activate()
        self.assertEqual(activated, [2])

    def test_lazy_submenu_and_duplicate_labels_keep_distinct_ids(self):
        root = (0, {}, [(1, {"label": "Recent", "children-display": "submenu"}, [])])
        with patch.object(search, "clean_label", wraps=search.clean_label):
            commands = search.flatten_dbusmenu(root, lambda _: (1, {}, [(2, {"label": "same"}, []), (3, {"label": "same"}, [])]), lambda _: None)
        self.assertEqual([c.identifier for c in commands], [2, 3])

    def test_rofi_selection_is_a_validated_index_and_cancel_is_inert(self):
        commands = [search.Command("$(never-run) <b>literal</b>", lambda: self.fail("executed"))]
        for code, output, expected in [(0, "0\n", 0), (1, "0", None), (0, "9", None), (0, "-1", None), (0, "0; rm", None)]:
            with patch.object(search.subprocess, "run", return_value=SimpleNamespace(returncode=code, stdout=output)) as run:
                self.assertEqual(search.choose(commands, "/pinned/rofi", "Test app"), expected)
                self.assertNotIn("shell", run.call_args.kwargs)
                self.assertNotIn("-markup-rows", run.call_args.args[0])
                self.assertIn("-no-custom", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
