"""Timeline format and battle execution independent of the GUI and MaaFramework."""

from dataclasses import dataclass
import json
from pathlib import Path
import re
from time import monotonic, sleep
from typing import Callable, Protocol

SLOTS = (5, 4, 3, 2, 1)
MAX_SECONDS = 90


def parse_clock(value: str) -> int:
    """Convert a displayed countdown (M:SS) to remaining seconds."""
    if not re.fullmatch(r'[01]:[0-5][0-9]', value):
        raise ValueError('时间格式应为 1:20 或 0:45。')
    minutes, seconds = map(int, value.split(':'))
    total = 60 * minutes + seconds
    if total > MAX_SECONDS:
        raise ValueError('时间不能超过 1:30。')
    return total


def clock(seconds: int) -> str:
    return f'{seconds // 60}:{seconds % 60:02d}'


@dataclass(frozen=True)
class Step:
    seconds: int
    slot: int
    sets: frozenset[int]


@dataclass(frozen=True)
class Timeline:
    title: str
    team_size: int
    auto: bool
    initial_sets: frozenset[int]
    steps: tuple[Step, ...]
    debug_screenshots: bool = False

    @classmethod
    def from_data(cls, data: dict) -> 'Timeline':
        """Validate and load a version 1 timeline. The mask always runs from slot 5 to 1."""
        if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1:
            raise ValueError('不支持此战斗轴文件版本。')
        title, size, auto = (data.get(key) for key in ('title', 'team_size', 'auto'))
        if not isinstance(title, str) or not title.strip() or type(size) is not int or not 1 <= size <= 5:
            raise ValueError('请输入标题并选择 1 到 5 名角色。')
        if type(auto) is not bool:
            raise ValueError('请选择开场 AUTO 状态。')
        debug_screenshots = data.get('debug_screenshots', False)
        if type(debug_screenshots) is not bool:
            raise ValueError('调试截图选项必须为开或关。')

        def read_sets(mask):
            if not isinstance(mask, str) or not re.fullmatch(r'[OX]{5}', mask):
                raise ValueError('SET 配置需要按 5→1 指定五个开关。')
            if 'O' in mask[:5 - size]:
                raise ValueError('空槽位无法开启 SET。')
            return frozenset(slot for slot, state in zip(SLOTS, mask) if state == 'O')

        initial = read_sets(data.get('initial_set'))
        rows = data.get('steps')
        if not isinstance(rows, list):
            raise ValueError('战斗轴的步骤列表无效。')
        steps = []
        previous = MAX_SECONDS
        for index, row in enumerate(rows, 1):
            try:
                if not isinstance(row, dict) or not isinstance(row.get('time'), str):
                    raise ValueError('缺少倒计时。')
                seconds, slot = parse_clock(row['time']), row.get('slot')
                if seconds == 0 or seconds > previous:
                    raise ValueError('时间应按倒计时顺序排列，且至少为 0:01。')
                if type(slot) is not int or not 1 <= slot <= size:
                    raise ValueError('请选择实际编入的角色槽位。')
                steps.append(Step(seconds, slot, read_sets(row.get('set'))))
                previous = seconds
            except ValueError as error:
                raise ValueError(f'第 {index} 行：{error}') from error
        return cls(title.strip(), size, auto, initial, tuple(steps), debug_screenshots)

    def to_data(self) -> dict:
        def mask(slots):
            return ''.join('O' if slot in slots else 'X' for slot in SLOTS)

        return {
            'version': 1, 'title': self.title, 'team_size': self.team_size, 'auto': self.auto,
            'initial_set': mask(self.initial_sets), 'debug_screenshots': self.debug_screenshots,
            'steps': [{'time': clock(step.seconds), 'slot': step.slot, 'set': mask(step.sets)}
                      for step in self.steps],
        }

    @classmethod
    def load(cls, path: Path) -> 'Timeline':
        return cls.from_data(json.loads(path.read_text(encoding='utf-8-sig')))

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(json.dumps(self.to_data(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)


@dataclass(frozen=True)
class SlotState:
    set_on: bool | None
    tp: float | None
    point: tuple[int, int]


@dataclass(frozen=True)
class BattleFrame:
    seconds: int
    auto: bool | None
    slots: dict[int, SlotState]
    set_all: bool | None = None
    interactive: bool = True


class BattleIO(Protocol):
    def setup_button(self) -> tuple[int, int] | None: ...
    def observe(self) -> BattleFrame | str | None: ...
    def click(self, point: tuple[int, int]) -> None: ...
    def record_step(self, label: str) -> None: ...
    def stopped(self) -> bool: ...


class BattleError(RuntimeError):
    pass


class UBFinder:
    """Detect a slot's high-to-low TP edge across readable battle HUDs."""

    def __init__(self):
        self.high_samples: dict[int, tuple[float, int, float]] = {}

    def update(self, frame: BattleFrame, now: float) -> set[int]:
        fired = set()
        for slot, state in frame.slots.items():
            if state.tp is None:
                continue
            if state.tp >= .84:
                self.high_samples[slot] = (state.tp, frame.seconds, now)
                continue
            before = self.high_samples.get(slot)
            if before is None:
                continue
            tp, seconds, timestamp = before
            if not (0 <= seconds - frame.seconds <= 1 and now - timestamp <= 8):
                del self.high_samples[slot]
            elif state.tp <= .38 and tp - state.tp >= .52:
                fired.add(slot)
                del self.high_samples[slot]
        return fired


class BattleRunner:
    """Start once, match UB rows in order, and verify each input from a fresh frame."""

    def __init__(self, io: BattleIO, report: Callable[[str], None],
                 now=monotonic, wait=sleep):
        self.io, self.report, self.now, self.wait = io, report, now, wait
        self.ub = UBFinder()

    def _click(self, point, label):
        if self.io.stopped():
            raise BattleError('任务已停止。')
        self.io.click(point)
        self.io.record_step(label)

    @staticmethod
    def _changes(frame, target, auto):
        for slot, state in frame.slots.items():
            if state.set_on is not None and state.set_on != (slot in target):
                yield slot, state.point, slot in target
        if auto is not None and frame.auto is not None and frame.auto != auto:
            yield 0, (1220, 556), auto

    def run(self, timeline: Timeline):
        if self.io.stopped():
            raise BattleError('任务已停止。')
        button = self.io.setup_button()
        if button is None:
            raise BattleError('请停在公会战的队伍编组页，确认「战斗开始」按钮可见。')
        self._click(button, 'start-battle')
        self.report('战斗已开始，等待开场画面。')
        started = self.now()
        last_hud = started
        last_seconds = None
        jump_candidate = None
        applied = 0
        target = timeline.initial_sets
        auto = timeline.auto
        applying = True
        bulk_attempted = False
        setting_since = None
        pending = None
        expected = set(range(1, timeline.team_size + 1))
        # The startup overlay can hide the controls for several displayed seconds.
        first_step = timeline.steps[0].seconds if timeline.steps else 0
        last_setup_second = max(85, first_step)
        while not self.io.stopped():
            if self.now() - started > 900:
                raise BattleError('等待结算超时。')
            frame = self.io.observe()
            now = self.now()
            if frame == 'result':
                if applying or applied < len(timeline.steps):
                    raise BattleError(f'战斗已结算，仅完成 {applied}/{len(timeline.steps)} 行。')
                self.report(f'战斗已结算，完成 {applied} 行。')
                return
            if frame is None:
                if now - last_hud > 28:
                    raise BattleError('长时间无法确认战斗画面。')
                self.wait(.05)
                continue
            if set(frame.slots) != expected:
                raise BattleError(f'战斗画面检测到 {len(frame.slots)} 个槽位，轴配置为 {timeline.team_size} 人。')
            if last_seconds is not None and frame.seconds > last_seconds:
                self.wait(.035)
                continue
            if last_seconds is not None and last_seconds - frame.seconds > 2:
                if jump_candidate != frame.seconds:
                    jump_candidate = frame.seconds
                    self.wait(.035)
                    continue
            jump_candidate = None
            last_seconds, last_hud = frame.seconds, now
            fired = self.ub.update(frame, now)

            if applying:
                if setting_since is None:
                    setting_since = now
                if now - setting_since > 18:
                    raise BattleError('无法在限定时间内确认 SET 或 AUTO 状态。')
                if not frame.interactive:
                    self.wait(.035)
                    continue
                if pending is not None:
                    slot, desired, tapped_at = pending
                    if slot == -1:
                        matched = all(state.set_on == desired for state in frame.slots.values())
                    else:
                        actual = frame.auto if slot == 0 else frame.slots[slot].set_on
                        matched = actual == desired
                    if matched:
                        pending = None
                    elif slot == -1 and now - tapped_at >= .5:
                        # The start animation can swallow an otherwise valid bulk tap.
                        # Resume from the latest portrait states, including partial changes.
                        pending = None
                        self.report('批量 SET 未确认，逐个检查并调整角色。')
                    elif now - tapped_at > 3:
                        name = 'AUTO' if slot == 0 else f'{slot} 号位 SET'
                        raise BattleError(f'点击后未读到预期的 {name} 状态。')
                    else:
                        self.wait(.05)
                        continue
                changes = list(self._changes(frame, target, auto))
                known_sets = all(state.set_on is not None for state in frame.slots.values())
                if auto is not None and changes and frame.seconds < last_setup_second:
                    raise BattleError('开场设置尚未完成，已到达轴的执行时间或超过开场窗口。')
                phase = 'opening' if auto is not None else f'row-{applied + 1:02d}'
                set_changes = sum(slot != 0 for slot, _, _ in changes)
                if (not bulk_attempted and known_sets
                        and (not target or target == expected) and set_changes > 1
                        and frame.set_all == (not bool(target))
                        and (target or all(state.set_on for state in frame.slots.values()))):
                    bulk_attempted = True
                    self.report(f'{clock(frame.seconds)} 尝试批量{"开启" if target else "关闭"} SET。')
                    self._click((1220, 458), f'{phase}-set-all-{"on" if target else "off"}')
                    pending = (-1, bool(target), self.now())
                    continue
                if changes:
                    slot, point, desired = changes[0]
                    name = 'AUTO' if slot == 0 else f'{slot} 号位 SET'
                    operation = '开启' if desired else '关闭'
                    self.report(f'{clock(frame.seconds)} {operation}{name}。')
                    control = 'auto' if slot == 0 else f'set-slot-{slot}'
                    self._click(point, f'{phase}-{control}-{"on" if desired else "off"}')
                    pending = (slot, desired, self.now())
                    continue
                if not known_sets or (auto is not None and frame.auto is None):
                    self.wait(.05)
                    continue
                if auto is not None:
                    self.report('开场 SET 和 AUTO 已确认。')
                else:
                    applied += 1
                    self.report(f'第 {applied} 行 SET 已确认。')
                self.io.record_step(f'{phase}-confirmed')
                applying, setting_since, auto = False, None, None

            if applied < len(timeline.steps):
                step = timeline.steps[applied]
                if frame.seconds < step.seconds:
                    raise BattleError(f'错过第 {applied + 1} 行：{clock(step.seconds)} {step.slot} 号位 UB。')
                if frame.seconds == step.seconds and step.slot in fired:
                    fired.clear()
                    target, applying = step.sets, True
                    bulk_attempted = False
                    self.report(f'{clock(step.seconds)} 检测到 {step.slot} 号位 UB，开始调整 SET。')
            self.wait(.035)
        raise BattleError('任务已停止。')
