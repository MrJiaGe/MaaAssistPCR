"""Bridge the Maa custom action to the editor and run the validated timeline."""

import logging
from threading import Event, Lock

from maa.custom_action import CustomAction

from battle import BattleError, BattleRunner
from editor import EditorRequest
from vision import MaaBattleIO


class RunBattle(CustomAction):
    def __init__(self, requests, debug_directory):
        super().__init__()
        self.requests = requests
        self.debug_directory = debug_directory
        self.lock = Lock()

    def run(self, context, argv):
        if not self.lock.acquire(blocking=False):
            logging.error('已有一个战斗编辑器在运行。')
            return False
        request = None
        io = None
        try:
            io = MaaBattleIO(context, Event())
            request = EditorRequest(io.preview())
            io.cancelled = request.cancelled
            self.requests.put(request)
            while not request.start.wait(.1):
                if io.stopped():
                    request.updates.put(('dismiss', '任务已停止。'))
                    return False
            if request.timeline is None or io.stopped():
                return False

            def report(message):
                logging.info('%s', message)
                request.updates.put(('status', message))

            if request.timeline.debug_screenshots:
                directory = io.enable_debug(self.debug_directory)
                report(f'调试截图将保存到 {directory}。')
            BattleRunner(io, report).run(request.timeline)
            request.updates.put(('done', '战斗已结算，排轴已完成。'))
            return True
        except BattleError as error:
            logging.warning('%s', error)
            if request:
                request.updates.put(('done', str(error)))
            return False
        except Exception:
            logging.exception('战斗任务失败')
            if request:
                request.updates.put(('done', '战斗任务失败，详情见 debug/battle-agent.log。'))
            return False
        finally:
            if io is not None:
                io.close_debug()
            self.lock.release()
