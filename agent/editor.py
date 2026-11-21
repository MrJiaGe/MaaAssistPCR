"""Graphical timeline editor. Tk stays on the Agent's main thread."""

from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from threading import Event
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from battle import SLOTS, Step, Timeline, clock, parse_clock


@dataclass
class EditorRequest:
    preview: object
    start: Event = field(default_factory=Event)
    cancelled: Event = field(default_factory=Event)
    updates: Queue = field(default_factory=Queue)
    timeline: Timeline | None = None


class Editor:
    def __init__(self, root, request: EditorRequest, config: Path):
        self.request, self.config = request, config
        self.window = tk.Toplevel(root)
        self.window.title('MaaAssistPCR · 公会战打轴')
        self.window.minsize(700, 580)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.bind('<Escape>', lambda event: self.close())
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)
        self.title = tk.StringVar(value='公会战练习轴')
        self.size = tk.IntVar(value=5)
        self.auto = tk.BooleanVar(value=True)
        self.debug_screenshots = tk.BooleanVar(value=False)
        self.initial = {slot: tk.BooleanVar(value=True) for slot in SLOTS}
        self.row_sets = {slot: tk.BooleanVar(value=True) for slot in SLOTS}
        self.time = tk.StringVar(value='1:20')
        self.slot = tk.IntVar(value=1)
        self.status = tk.StringVar(value='选择开场设置，添加需要等待的 UB。')
        self.steps: list[Step] = []
        self.running = False
        self.apply_widgets = []
        self.size_widgets: dict[int, list] = {slot: [] for slot in SLOTS}
        self.build()
        if config.is_file():
            try:
                self.load(Timeline.load(config))
            except (OSError, ValueError) as error:
                self.status.set(f'读取上次的战斗轴失败。{error}')
        self.window.lift()
        self.window.after(75, self.poll)

    def build(self):
        main = ttk.Frame(self.window, padding=16)
        main.grid(sticky='nsew')
        main.columnconfigure(1, weight=1)
        main.rowconfigure(5, weight=1)
        ttk.Label(main, text='战斗轴').grid(row=0, column=0, sticky='w', padx=(0, 8))
        title = ttk.Entry(main, textvariable=self.title)
        title.grid(row=0, column=1, sticky='ew')
        self.apply_widgets.append(title)
        for index, (label, command) in enumerate((('打开…', self.open_file), ('另存…', self.save_file)), 2):
            button = ttk.Button(main, text=label, command=command)
            button.grid(row=0, column=index, padx=(6, 0))
            self.apply_widgets.append(button)

        if self.request.preview is None:
            ttk.Label(main, text='请在游戏里手动编队，停在「队伍编组」页。').grid(
                row=1, columnspan=4, pady=(10, 4))
        else:
            preview = Image.fromarray(self.request.preview)
            preview.thumbnail((580, 110))
            self.preview = ImageTk.PhotoImage(preview, master=self.window)
            ttk.Label(main, image=self.preview).grid(row=1, columnspan=4, pady=(10, 4))

        options = ttk.LabelFrame(main, text='开场 · 1:30', padding=(10, 6))
        options.grid(row=2, columnspan=4, sticky='ew', pady=(4, 8))
        ttk.Label(options, text='角色人数').grid(row=0, column=0, sticky='w')
        size = ttk.Combobox(options, textvariable=self.size, values=(1, 2, 3, 4, 5),
                            width=3, state='readonly')
        size.grid(row=0, column=1, padx=(8, 12))
        size.bind('<<ComboboxSelected>>', self.size_changed)
        auto = ttk.Checkbutton(options, text='AUTO', variable=self.auto)
        auto.grid(row=0, column=2, sticky='w')
        debug = ttk.Checkbutton(options, text='保存调试截图', variable=self.debug_screenshots)
        debug.grid(row=0, column=3, columnspan=3, padx=(12, 0), sticky='w')
        self.apply_widgets.extend([size, auto, debug])
        self.slot_controls(options, 1, 0, self.initial, '开场 SET')

        edit = ttk.LabelFrame(main, text='UB 触发与 SET 调整', padding=(10, 6))
        edit.grid(row=3, columnspan=4, sticky='ew')
        ttk.Label(edit, text='倒计时').grid(row=0, column=0, sticky='w')
        time = ttk.Entry(edit, textvariable=self.time, width=8)
        time.grid(row=0, column=1, padx=(0, 6), sticky='w')
        self.apply_widgets.append(time)
        ttk.Label(edit, text='释放 UB 的槽位').grid(row=1, column=0, sticky='w')
        for column, slot in enumerate(SLOTS, 1):
            radio = ttk.Radiobutton(edit, text=str(slot), variable=self.slot, value=slot)
            radio.grid(row=1, column=column, padx=5, sticky='w')
            self.apply_widgets.append(radio)
            self.size_widgets[slot].append(radio)
        self.slot_controls(edit, 2, 0, self.row_sets, '调整后 SET')
        actions = ttk.Frame(main)
        actions.grid(row=4, columnspan=4, sticky='w', pady=6)
        for caption, command in (('添加', self.add), ('更新选中行', self.update), ('删除选中行', self.remove)):
            button = ttk.Button(actions, text=caption, command=command)
            button.pack(side='left', padx=(0, 6))
            self.apply_widgets.append(button)

        list_panel = ttk.Frame(main)
        list_panel.grid(row=5, columnspan=4, sticky='nsew')
        list_panel.columnconfigure(0, weight=1)
        list_panel.rowconfigure(0, weight=1)
        self.table = ttk.Treeview(list_panel, columns=('clock', 'slot', 'set'), show='headings',
                                  selectmode='browse', height=4)
        for key, label in (('clock', '倒计时'), ('slot', '释放 UB'), ('set', 'SET  5 → 1')):
            self.table.heading(key, text=label)
            self.table.column(key, width=125, anchor='center')
        self.table.grid(sticky='nsew')
        scrollbar = ttk.Scrollbar(list_panel, orient='vertical', command=self.table.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.bind('<<TreeviewSelect>>', self.select)
        ttk.Label(main, wraplength=560, textvariable=self.status).grid(row=6, columnspan=2, sticky='w', pady=(10, 0))
        self.start_button = ttk.Button(main, text='开始战斗', command=self.launch)
        self.start_button.grid(row=6, column=2, sticky='e', padx=(6, 0), pady=(10, 0))
        self.close_button = ttk.Button(main, text='关闭', command=self.close)
        self.close_button.grid(row=6, column=3, sticky='e', padx=(6, 0), pady=(10, 0))

    def slot_controls(self, frame, row, column, variables, label):
        ttk.Label(frame, text=label).grid(row=row, column=column, sticky='w')
        for column, slot in enumerate(SLOTS, column + 1):
            toggle = ttk.Checkbutton(frame, text=str(slot), variable=variables[slot])
            toggle.grid(row=row, column=column, padx=5, sticky='w')
            self.apply_widgets.append(toggle)
            self.size_widgets[slot].append(toggle)

    def size_changed(self, _event=None):
        for slot, widgets in self.size_widgets.items():
            active = slot <= self.size.get()
            for widget in widgets:
                widget.state(['!disabled' if active else 'disabled'])
            if not active:
                self.initial[slot].set(False)
                self.row_sets[slot].set(False)
        if self.slot.get() > self.size.get():
            self.slot.set(1)

    def selected_index(self):
        selected = self.table.selection()
        return int(selected[0]) if selected else None

    def select(self, _event):
        index = self.selected_index()
        if index is None:
            return
        step = self.steps[index]
        self.time.set(clock(step.seconds))
        self.slot.set(step.slot if step.slot <= self.size.get() else 1)
        for slot in SLOTS:
            self.row_sets[slot].set(slot in step.sets and slot <= self.size.get())

    def refresh(self, selected=None):
        items = self.table.get_children()
        if items:
            self.table.delete(*items)
        for index, step in enumerate(self.steps):
            mask = ' '.join('开' if slot in step.sets else '关' for slot in SLOTS)
            self.table.insert('', 'end', iid=str(index), values=(clock(step.seconds), f'{step.slot} 号位', mask))
        if selected is not None:
            self.table.selection_set(str(selected))
            self.table.see(str(selected))

    def edit(self, index=None):
        try:
            step = Step(parse_clock(self.time.get().strip()), self.slot.get(), self.enabled(self.row_sets))
            if step.seconds == 0 or not 1 <= step.slot <= self.size.get():
                raise ValueError('请选择 0:01 至 1:30 和队伍中实际存在的槽位。')
            steps = self.steps.copy()
            if index is None:
                index = len(steps)
                steps.append(step)
            else:
                steps[index] = step
            order = sorted(range(len(steps)), key=lambda i: -steps[i].seconds)
            self.steps = [steps[i] for i in order]
            self.refresh(order.index(index))
        except ValueError as error:
            self.status.set(str(error))

    def add(self):
        self.edit()

    def update(self):
        index = self.selected_index()
        if index is not None:
            self.edit(index)

    def remove(self):
        index = self.selected_index()
        if index is not None:
            del self.steps[index]
            self.refresh()

    def load(self, timeline):
        self.title.set(timeline.title)
        self.size.set(timeline.team_size)
        self.auto.set(timeline.auto)
        self.debug_screenshots.set(timeline.debug_screenshots)
        for slot in SLOTS:
            self.initial[slot].set(slot in timeline.initial_sets)
        self.steps = list(timeline.steps)
        self.size_changed()
        self.refresh()

    def enabled(self, states):
        return frozenset(slot for slot, value in states.items() if value.get())

    def timeline(self):
        candidate = Timeline(self.title.get(), self.size.get(), self.auto.get(),
                             self.enabled(self.initial), tuple(self.steps), self.debug_screenshots.get())
        return Timeline.from_data(candidate.to_data())

    def open_file(self):
        file = filedialog.askopenfilename(parent=self.window, filetypes=[('战斗轴', '*.json')])
        if file:
            try:
                self.load(Timeline.load(Path(file)))
            except (OSError, ValueError) as error:
                self.status.set(str(error))

    def save_file(self):
        try:
            timeline = self.timeline()
            file = filedialog.asksaveasfilename(parent=self.window, defaultextension='.json',
                                               filetypes=[('战斗轴', '*.json')])
            if file:
                timeline.save(Path(file))
        except (OSError, ValueError) as error:
            self.status.set(str(error))

    def launch(self):
        try:
            timeline = self.timeline()
            if not messagebox.askyesno('开始战斗', '请确认模拟器已停在你要开始的队伍编组页。', parent=self.window):
                return
            timeline.save(self.config)
        except (OSError, ValueError) as error:
            self.status.set(str(error))
            return
        self.request.timeline = timeline
        for widget in self.apply_widgets:
            widget.state(['disabled'])
        self.start_button.state(['disabled'])
        self.close_button.configure(text='停止')
        self.running = True
        self.request.start.set()

    def close(self):
        self.request.cancelled.set()
        self.request.start.set()
        if self.running:
            self.status.set('正在停止…')
        else:
            self.window.destroy()

    def poll(self):
        while True:
            try:
                kind, message = self.request.updates.get_nowait()
            except Empty:
                break
            self.status.set(message)
            if kind == 'done':
                self.running = False
                self.close_button.configure(text='关闭')
            elif kind == 'dismiss' and not self.running:
                self.close()
                return
        self.window.after(75, self.poll)
