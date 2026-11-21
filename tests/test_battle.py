"""Replay battle observations to cover timing, slots and verified device input."""

from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent'))
from battle import BattleError, BattleFrame, BattleRunner, SlotState, Timeline, UBFinder
from vision import MaaBattleIO, _button, _origins, read_slots


def script(auto=True, initial='OOOOO', steps=()):
    return Timeline.from_data({'version': 1, 'title': '训练', 'team_size': 5, 'auto': auto,
                               'initial_set': initial, 'steps': list(steps)})


def frame(time, set_mask='OOOOO', auto=True, tp3=.4, *, interactive=True):
    slots = {slot: SlotState(on == 'O', tp3 if slot == 3 else .3, (x, 585))
             for slot, on, x in zip(range(5, 0, -1), set_mask, range(319, 960, 160))}
    return BattleFrame(time, auto, slots, set_mask == 'OOOOO', interactive)


class Replay:
    def __init__(self, frames=(), *, button=(1132, 602), stopped=False):
        self.frames = iter(frames)
        self.clicks = []
        self.recorded = []
        self.button = button
        self.cancel = stopped
        self.time = 0.0

    def setup_button(self):
        return self.button

    def observe(self):
        self.time += .1
        return next(self.frames)

    def click(self, point):
        self.clicks.append(point)

    def record_step(self, label):
        self.recorded.append(label)

    def stopped(self):
        return self.cancel

    def run(self, timeline):
        BattleRunner(self, lambda message: None, now=lambda: self.time, wait=lambda _: None).run(timeline)


class BattleTest(unittest.TestCase):
    def test_5_to_1_set_and_slot_order(self):
        row = {'time': '1:20', 'slot': 3, 'set': 'XOXXO'}
        timeline = script(steps=[row])
        self.assertEqual(timeline.steps[0].sets, {4, 1})
        self.assertEqual(Timeline.from_data(timeline.to_data()), timeline)
        self.assertFalse(timeline.debug_screenshots)
        self.assertTrue(Timeline.from_data(dict(timeline.to_data(), debug_screenshots=True)).debug_screenshots)
        invalid = {**timeline.to_data(), 'team_size': 3}
        with self.assertRaises(ValueError):
            Timeline.from_data(invalid)

    def test_matches_ub_and_verifies_changes_within_frozen_clock(self):
        row = {'time': '1:20', 'slot': 3, 'set': 'XOXXO'}
        replay = Replay([frame(87), frame(85), frame(83), frame(81, tp3=.97), None, frame(80, tp3=.67),
                         frame(80, tp3=.23), frame(80, interactive=False), frame(80),
                         frame(80, 'XOOOO'), frame(80, 'XOXOO'), frame(79, 'XOXXO'), 'result'])
        replay.run(script(steps=[row]))
        self.assertEqual(replay.clicks, [(1132, 602), (319, 585), (639, 585), (799, 585)])
        self.assertEqual(replay.recorded, ['start-battle', 'opening-confirmed', 'row-01-set-slot-5-off',
                                          'row-01-set-slot-3-off', 'row-01-set-slot-2-off', 'row-01-confirmed'])

    def test_same_second_requires_distinct_ub_edges(self):
        row = {'time': '1:20', 'slot': 3, 'set': 'OOOOO'}
        replay = Replay([frame(87), frame(80, tp3=1), frame(80, tp3=1), frame(80, tp3=.1),
                         frame(80, tp3=.1), frame(79, tp3=.15)])
        with self.assertRaisesRegex(BattleError, '第 2 行'):
            replay.run(script(steps=[row, row]))
        self.assertEqual(replay.clicks, [(1132, 602)])

    def test_opening_adjusts_auto_after_set(self):
        replay = Replay([frame(87, 'XXXXX', False), frame(87, 'OOOOO', False), frame(86), 'result'])
        replay.run(script())
        self.assertEqual(replay.clicks, [(1132, 602), (1220, 458), (1220, 556)])

    def test_opening_recovers_when_bulk_click_is_ignored(self):
        off = frame(90, 'XXXXX')
        replay = Replay([off] * 7 + [frame(89, mask) for mask in
                                     ('OXXXX', 'OOXXX', 'OOOXX', 'OOOOX', 'OOOOO')] + ['result'])
        replay.run(script())
        self.assertEqual(replay.clicks, [(1132, 602), (1220, 458), (319, 585), (479, 585),
                                        (639, 585), (799, 585), (959, 585)])

    def test_opening_fallback_preserves_partial_bulk_changes(self):
        off = frame(90, 'XXXXX')
        partial = frame(90, 'XOXOO')
        replay = Replay([off] + [partial] * 6 + [frame(89, 'OOXOO'), frame(89), 'result'])
        replay.run(script())
        self.assertEqual(replay.clicks, [(1132, 602), (1220, 458), (319, 585), (639, 585)])

    def test_wrong_screen_and_cancellation_never_click(self):
        for replay in (Replay(button=None), Replay(stopped=True)):
            with self.assertRaises(BattleError):
                replay.run(script())
            self.assertEqual(replay.clicks, [])

    def test_finder_ignores_small_drain_and_stale_sample(self):
        detector = UBFinder()
        detector.update(frame(81, tp3=.97), 1)
        for reading, now in ((frame(81, tp3=.62), 1.2), (frame(79, tp3=.30), 2),
                             (frame(78, tp3=.93), 2.5), (frame(78, tp3=.10), 12)):
            self.assertEqual(detector.update(reading, now), set())

    def test_debug_capture_waits_100ms_and_reuses_frame(self):
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        io = MaaBattleIO(SimpleNamespace(tasker=SimpleNamespace(controller=None, stopping=False)), Event())
        io.screenshot = Mock(return_value=image)
        io.read_frame = Mock(return_value='result')
        with patch('vision.sleep') as pause:
            io.record_step('disabled')
            pause.assert_not_called()
            io.screenshot.assert_not_called()
            io.debug_dir = Path('debug/battle-steps/test')
            io.debug_writer = Mock()
            io.record_step('opening-set-slot-5-on')
            pause.assert_called_once_with(.1)
        save, path, captured = io.debug_writer.submit.call_args.args
        self.assertEqual(path.name, '0001_opening-set-slot-5-on.png')
        self.assertIs(captured, image)
        self.assertEqual(io.observe(), 'result')
        io.screenshot.assert_called_once()
        self.assertIs(io.read_frame.call_args.args[0], image)

    def test_slot_detection_recognizes_live_hud_geometry(self):
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)
        for x in (255, 415, 575, 735, 895):
            screen[663, x + 6:x + 126] = 230
            screen[689, x + 6:x + 126] = 230
        screen[696:700, 261:320] = (255, 210, 50)
        screen[517:547, 366:396] = (235, 181, 5)
        screen[555:621, 255:259] = (230, 223, 33)
        screen[548:564, 1190:1250] = 232
        slots = read_slots(screen, _origins(screen))
        self.assertEqual(list(slots), [5, 4, 3, 2, 1])
        self.assertAlmostEqual(slots[5].tp, .5)
        self.assertTrue(slots[5].set_on)
        self.assertFalse(slots[4].set_on)
        self.assertFalse(_button(screen, 556))
        screen[696:700, 261:379] = 255
        self.assertIsNone(read_slots(screen, _origins(screen))[5].tp)


if __name__ == '__main__':
    unittest.main()
