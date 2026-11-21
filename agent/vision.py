"""Recognize the Chinese Android battle HUD in the controller's 1280×720 frame."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import logging
from time import monotonic, sleep

import numpy as np
from PIL import Image

from battle import BattleError, BattleFrame, SlotState, parse_clock

FRAME_SHAPE = (720, 1280, 3)
DEBUG_CAPTURE_DELAY = .1


def _runs(mask):
    edges = np.diff(np.r_[False, mask, False].astype(np.int8))
    return zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))


def _blue(pixels):
    blue, green, red = np.moveaxis(pixels.astype(np.int16), -1, 0)
    return (blue > 135) & (green > 95) & (blue - red > 45) & (green - red > 35)


def _button(frame, y):
    # Both flanks avoid the dark text and the animated highlight in the center.
    left = frame[y - 8:y + 8, 1190:1201]
    right = frame[y - 8:y + 8, 1239:1250]
    left_blue, right_blue = (_blue(side).mean() for side in (left, right))
    if min(left_blue, right_blue) > .70:
        return True
    if min((side.min(axis=2) > 185).mean() for side in (left, right)) > .72:
        return False
    return None


def _origins(frame):
    """Pair the bright top edges of the HP and TP bars, independent of fill."""
    hp_edge = frame[663, 110:1160].min(axis=1) > 190
    tp_edge = frame[689, 110:1160].min(axis=1) > 190
    starts = []
    for left, right in _runs(hp_edge & tp_edge):
        if 110 <= right - left <= 124:
            starts.append(int(left) + 110 - 6)
    if len(starts) > 5 or any(not 154 <= b - a <= 166 for a, b in zip(starts, starts[1:])):
        return ()
    return tuple(starts)


def _tp(frame, x):
    # The colored fill grows from the left. Require a colored or dark interior so
    # a white flash, faded portrait, or transient overlay cannot read as empty.
    strip = frame[696:700, x + 6:x + 124]
    blue = (_blue(strip).sum(axis=0) >= 2)
    dark = (strip.max(axis=2) < 135).sum(axis=0) >= 2
    if (blue | dark).mean() < .91:
        return None
    filled = int(blue.sum())
    if blue[:filled].sum() < max(0, filled - 5):
        return None
    return filled / len(blue)


def _set(frame, x):
    center = frame[517:547, x + 111:x + 141]
    border = frame[555:621, x:x + 4]
    badge, outline = _blue(center).mean(), _blue(border).mean()
    if badge >= .36 and outline >= .27:
        return True
    if badge < .22 and outline < .18:
        return False
    return None


def read_slots(frame, origins):
    """Read each locked slot. Physical left-to-right order is highest to lowest."""
    return {slot: SlotState(_set(frame, x), _tp(frame, x), (x + 63, 585))
            for slot, x in zip(range(len(origins), 0, -1), origins)}


class MaaBattleIO:
    """Use the current task's controller and versioned Pipeline OCR nodes."""

    def __init__(self, context, cancelled):
        self.context = context
        self.tasker = context.tasker
        self.controller = self.tasker.controller
        self.cancelled = cancelled
        self.origins = ()
        self.result_checked = 0.0
        self.debug_dir = None
        self.debug_writer = None
        self.debug_sequence = 0
        self.debug_frame = None

    def enable_debug(self, directory):
        """Create a directory and a background PNG writer just for this battle."""
        name = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        self.debug_dir = directory / name
        self.debug_dir.mkdir(parents=True, exist_ok=False)
        self.debug_writer = ThreadPoolExecutor(max_workers=1)
        return self.debug_dir

    def close_debug(self):
        if self.debug_writer is not None:
            self.debug_writer.shutdown(wait=True)

    @staticmethod
    def _save_debug_png(path, frame):
        try:
            Image.fromarray(np.ascontiguousarray(frame[:, :, ::-1])).save(path, compress_level=1)
        except (OSError, ValueError):
            logging.exception('无法保存调试截图 %s', path)

    def record_step(self, label):
        """Capture after the step's UI delay and reuse the frame for the next observation."""
        if self.debug_writer is None or self.stopped():
            return
        sleep(DEBUG_CAPTURE_DELAY)
        if self.stopped():
            return
        try:
            frame = self.screenshot()
        except BattleError as error:
            logging.warning('调试截图失败 [%s]。%s', label, error)
            return
        self.debug_sequence += 1
        path = self.debug_dir / f'{self.debug_sequence:04d}_{label}.png'
        self.debug_frame = frame
        self.debug_writer.submit(self._save_debug_png, path, frame)

    def stopped(self) -> bool:
        return self.cancelled.is_set() or self.tasker.stopping

    def screenshot(self):
        job = self.controller.post_screencap().wait()
        if not job.succeeded:
            raise BattleError('模拟器截图失败。')
        frame = job.get()
        if frame is None or frame.shape != FRAME_SHAPE:
            raise BattleError('战斗任务需要 16:9 横屏和 1280×720 的控制器画面。')
        return frame

    def _recognize(self, name, frame):
        return self.context.run_recognition(name, frame)

    def _hit(self, name, frame):
        result = self._recognize(name, frame)
        return result if result and result.hit else None

    def setup_button(self):
        frame = self.screenshot()
        return self.start_point(frame)

    def start_point(self, frame):
        if not self._hit('PCRFormationPage', frame):
            return None
        button = self._hit('PCRBattleStartButton', frame)
        if button and button.box:
            x, y, w, h = button.box
            return x + w // 2, y + h // 2
        return None

    def preview(self):
        frame = self.screenshot()
        if self.start_point(frame) is None:
            return None
        return frame[536:676, 52:785, ::-1].copy()

    def observe(self):
        frame, self.debug_frame = self.debug_frame, None
        return self.read_frame(self.screenshot() if frame is None else frame)

    def read_frame(self, frame):
        auto, set_all = _button(frame, 556), _button(frame, 458)
        origins = _origins(frame)
        if origins and (not self.origins or len(origins) == len(self.origins)) and auto is not None:
            hit = self._hit('PCRBattleClock', frame)
            raw = getattr(hit.best_result, 'text', '') if hit else ''
            try:
                seconds = parse_clock(raw.strip().replace('：', ':'))
            except ValueError:
                return None
            if not self.origins:
                self.origins = origins
            if max(abs(a - b) for a, b in zip(origins, self.origins)) > 3:
                return None
            return BattleFrame(seconds, auto, read_slots(frame, self.origins), set_all,
                               interactive=set_all is not None)
        if monotonic() - self.result_checked > .65:
            self.result_checked = monotonic()
            if self._hit('PCRResultNext', frame) and self._hit('PCRDamageReport', frame):
                return 'result'
        return None

    def click(self, point):
        if self.stopped():
            raise BattleError('任务已停止。')
        if not self.controller.post_click(*point).wait().succeeded:
            raise BattleError('模拟器点击失败。')
