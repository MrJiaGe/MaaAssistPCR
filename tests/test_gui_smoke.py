"""Verify the packaged PI and execute its smoke node without a real device."""

from importlib.metadata import version
import json
import os
from pathlib import Path
import unittest

from maa.controller import CustomController
from maa.library import Library
from maa.resource import Resource
from maa.tasker import Tasker
import numpy as np


class OfflineController(CustomController):
    """Provide a frame if requested and record any attempt to operate a device."""

    def __init__(self):
        super().__init__()
        self.input_attempts = 0

    def connect(self):
        return True

    def request_uuid(self):
        return "maaassistpcr-test"

    def screencap(self):
        return np.zeros((720, 1280, 3), dtype=np.uint8)

    def reject_input(self, *args):
        self.input_attempts += 1
        return False

    start_app = stop_app = click = swipe = reject_input
    touch_down = touch_move = touch_up = reject_input
    click_key = input_text = key_down = key_up = reject_input


class GuiPackageTest(unittest.TestCase):
    def test_packaged_smoke_task(self):
        root = Path(os.environ.get("MAA_GUI_PACKAGE", "install/MaaAssistPCR-win-x64")).resolve()
        self.assertTrue((root / "MFAAvalonia.exe").is_file(), root)
        native = root / "runtimes/win-x64/native"
        self.assertTrue((native / "MaaAdbControlUnit.dll").is_file())
        Library.open(native)
        self.assertEqual(Library.framework_libpath, native / "MaaFramework.dll")
        self.assertEqual(Library.version().lstrip("v"), version("MaaFW").lstrip("v"))

        interface = json.loads((root / "interface.json").read_text(encoding="utf-8"))
        self.assertEqual(interface["interface_version"], 2)
        self.assertEqual(interface["name"], "MaaAssistPCR")
        self.assertEqual([controller["type"] for controller in interface["controller"]], ["Adb"])
        self.assertNotIn("agent", interface)
        task, = interface["task"]
        self.assertEqual(task["entry"], "GuiSmokeTest")

        resource = Resource()
        bundle, = interface["resource"]
        for path in bundle["path"]:
            self.assertTrue(resource.post_bundle(root / path).wait().status.succeeded, path)
        controller = OfflineController()
        self.assertTrue(controller.post_connection().wait().status.succeeded)
        tasker = Tasker()
        self.assertTrue(tasker.bind(resource, controller))
        self.assertTrue(tasker.post_task(task["entry"]).wait().status.succeeded)
        self.assertEqual(controller.input_attempts, 0)
