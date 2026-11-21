"""Verify the packaged GUI, no-input smoke task and OCR click without a device."""

from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import unittest

from maa.controller import CustomController
from maa.define import MaaControllerFeatureEnum
from maa.library import Library
from maa.resource import Resource
from maa.tasker import Tasker
import numpy as np
from PIL import Image


FIXTURES = Path(__file__).with_name("fixtures")


class OfflineController(CustomController):
    """Provide a frame if requested and record any attempt to operate a device."""

    def __init__(self, frame=None):
        super().__init__()
        self.frame = frame if frame is not None else np.zeros((720, 1280, 3), dtype=np.uint8)
        self.clicks = []
        self.input_attempts = 0

    def connect(self):
        return True

    def request_uuid(self):
        return "maaassistpcr-test"

    def get_features(self):
        return MaaControllerFeatureEnum.Null

    def screencap(self):
        return self.frame

    def click(self, x, y):
        self.clicks.append((x, y))
        return True

    def reject_input(self, *args):
        self.input_attempts += 1
        return False

    start_app = stop_app = swipe = reject_input
    touch_down = touch_move = touch_up = reject_input
    click_key = input_text = key_down = key_up = reject_input


class GuiPackageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ.get("MAA_GUI_PACKAGE", "install/MaaAssistPCR-win-x64")).resolve()
        native = cls.root / "runtimes/win-x64/native"
        Library.open(native)
        cls.interface = json.loads((cls.root / "interface.json").read_text(encoding="utf-8"))
        cls.resource = Resource()
        if not cls.resource.use_cpu():
            raise RuntimeError("Could not select CPU inference for the offline test.")
        bundle, = cls.interface["resource"]
        for path in bundle["path"]:
            if not cls.resource.post_bundle(cls.root / path).wait().status.succeeded:
                raise RuntimeError(f"Could not load packaged resource: {path}")

    def run_task(self, entry, frame=None):
        controller = OfflineController(frame)
        self.assertTrue(controller.post_connection().wait().status.succeeded)
        tasker = Tasker()
        self.assertTrue(tasker.bind(self.resource, controller))
        job = tasker.post_task(entry).wait()
        return job.status, job.get(), controller

    def test_packaged_smoke_task(self):
        native = self.root / "runtimes/win-x64/native"
        self.assertTrue((self.root / "MFAAvalonia.exe").is_file(), self.root)
        self.assertTrue((native / "MaaAdbControlUnit.dll").is_file())
        self.assertEqual(Library.framework_libpath, native / "MaaFramework.dll")
        self.assertEqual(Library.version().lstrip("v"), version("MaaFW").lstrip("v"))
        self.assertEqual(self.interface["interface_version"], 2)
        self.assertEqual(self.interface["name"], "MaaAssistPCR")
        self.assertEqual([controller["type"] for controller in self.interface["controller"]], ["Adb"])
        entries = {task["entry"] for task in self.interface["task"]}
        self.assertEqual(entries, {"GuiSmokeTest", "TitleOcrDemo", "PCRBattleTimeline"})

        status, _, controller = self.run_task("GuiSmokeTest")
        self.assertTrue(status.succeeded)
        self.assertEqual(controller.clicks, [])
        self.assertEqual(controller.input_attempts, 0)

    def test_packaged_agent_initializes(self):
        executable = self.root / self.interface['agent']['child_exec']
        self.assertTrue(executable.is_file())
        env = dict(os.environ, MAAFW_BINARY_PATH=str(self.root / 'missing-native-dir'))
        result = subprocess.run([str(executable), '--self-test'], cwd=self.root.parent, env=env, timeout=30)
        self.assertEqual(result.returncode, 0)

    @staticmethod
    def make_frame(fixture, x, y):
        with Image.open(FIXTURES / fixture) as image:
            bgr = np.asarray(image.convert("RGB"))[:, :, ::-1]
        h, w = bgr.shape[:2]
        frame = np.full((720, 1280, 3), 25, dtype=np.uint8)
        frame[y:y + h, x:x + w] = bgr
        return frame

    def assert_ocr_click(self, frame):
        status, detail, controller = self.run_task("TitleOcrDemo", frame)
        self.assertTrue(status.succeeded)
        self.assertEqual(controller.input_attempts, 0)
        self.assertEqual(len(controller.clicks), 1, controller.clicks)
        (click_x, click_y), = controller.clicks
        node, = [node for node in detail.nodes if node.name == "TitleOcrClick"]
        self.assertTrue(node.recognition.hit)
        x, y, w, h = node.recognition.box
        self.assertTrue(x <= click_x < x + w and y <= click_y < y + h)
        return click_x, click_y

    def test_ocr_clicks_detected_text(self):
        for x, y in ((470, 637), (524, 651)):
            with self.subTest(x=x, y=y):
                click_x, click_y = self.assert_ocr_click(self.make_frame("title_ocr_match.png", x, y))
                self.assertTrue(x <= click_x < x + 290 and y <= click_y < y + 48)

    def test_ocr_does_not_click_other_text(self):
        frame = self.make_frame("title_ocr_other.png", 480, 641)
        status, _, controller = self.run_task("TitleOcrDemo", frame)
        self.assertTrue(status.failed)
        self.assertEqual(controller.clicks, [])
        self.assertEqual(controller.input_attempts, 0)

    @unittest.skipUnless(os.environ.get("MAA_TITLE_SCREENSHOT"), "No local title screenshot supplied")
    def test_ocr_title_screenshot(self):
        with Image.open(os.environ["MAA_TITLE_SCREENSHOT"]) as image:
            frame = np.asarray(image.convert("RGB").resize((1280, 720), Image.Resampling.BILINEAR))
        click_x, click_y = self.assert_ocr_click(np.ascontiguousarray(frame[:, :, ::-1]))
        self.assertTrue(505 <= click_x < 777 and 650 <= click_y < 691)
