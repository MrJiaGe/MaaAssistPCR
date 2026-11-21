"""Start the Maa Agent and bridge its battle action to the timeline editor."""

import logging
import os
from pathlib import Path
from queue import Empty, Queue
import sys
from threading import Event, Thread
import tkinter as tk

from editor import Editor


def project_root():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parents[1]
    return Path(__file__).resolve().parents[1]


def main():
    root_dir = project_root()
    if getattr(sys, 'frozen', False):
        native = root_dir / 'runtimes/win-x64/native'
    else:
        native = root_dir / 'deps/bin'

    # MaaFW opens its binary directory during import, before any registration.
    os.environ['MAAFW_BINARY_PATH'] = str(native)
    with os.add_dll_directory(str(native)):
        from maa.agent.agent_server import AgentServer

        from battle_action import RunBattle

        requests = Queue()
        action = RunBattle(requests, root_dir / 'debug/battle-steps')
        if not AgentServer.register_custom_action('PCRBattleTimeline', action):
            return 1
        if sys.argv[-1] == '--self-test':
            return 0 if tk.Tcl().eval('info patchlevel') else 1
        root = tk.Tk()
        root.withdraw()
        server_done = Event()
        if len(sys.argv) < 2 or not AgentServer.start_up(sys.argv[-1]):
            root.destroy()
            return 1

        def join():
            AgentServer.join()
            server_done.set()

        def display_requests():
            if server_done.is_set():
                root.destroy()
                return
            try:
                request = requests.get_nowait()
            except Empty:
                pass
            else:
                if not request.cancelled.is_set():
                    Editor(root, request, root_dir / 'config/battle-timeline.json')
            root.after(50, display_requests)

        Thread(target=join, daemon=True).start()
        root.after(50, display_requests)
        try:
            root.mainloop()
        finally:
            AgentServer.shut_down()
    return 0


if __name__ == '__main__':
    log = project_root() / 'debug/battle-agent.log'
    log.parent.mkdir(exist_ok=True)
    logging.basicConfig(filename=log, encoding='utf-8', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        sys.exit(main())
    except Exception:
        logging.exception('无法启动战斗 Agent')
        sys.exit(1)
