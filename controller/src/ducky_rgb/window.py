"""Desktop editor and hardware diagnostics."""
from collections import deque
from copy import deepcopy
from dataclasses import asdict
from functools import partial
import platform
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QFileDialog,
    QFormLayout, QHBoxLayout, QInputDialog, QListWidget,
    QMainWindow, QMenu, QMessageBox, QScrollArea, QSplitter,
    QStyle, QSystemTrayIcon, QTabWidget, QTextEdit,
)

from .devices import Assignment, DUCKY, GROUPS, mapping_json, validate_mapping
from .effects import EFFECTS
from .engine import Layer, Renderer
from .keyboard import KeyboardView
from .layer_editor import LayerEditor
from .widgets import DARK, LIGHT, button, checkbox, label, number, panel
from .platforms import capability_report
from .simulator import SIMULATOR
from .storage import Profile, examples, read_json, validate_profile, write_json
from .worker import DeviceWorker, Metrics, Output


class MainWindow(QMainWindow):
    event = Signal(str, object)

    def __init__(self, storage, backends, startup, *, auto_simulate=False, profile_name=None):
        super().__init__()
        self.storage, self.backends, self.startup = storage, backends, startup
        self.device = DUCKY
        self.setWindowTitle("Ducky RGB Studio")
        self.resize(1320, 800)
        self.setMinimumSize(820, 570)
        self.history = deque(maxlen=60)
        self.undo_stack, self.redo_stack = [], []
        self.records = {}
        self.playing, self.tick_origin, self.frozen = True, time.monotonic(), 0.
        self.metrics, self.caps = Metrics(), None
        self.discovered, self.endpoint, self.external = [], None, False
        self.mapping, self.profiles = {}, examples()
        self.override = self.last_displayed_output = None
        self.calibration = False
        self.test_until = None
        self.benchmark_result = None
        self.rendered = 0
        self.previous_stats = (time.monotonic(), 0, Metrics())
        self.settings = {"dark": True, "fast": True, "reconnect": True, "tray": False, "index": 0,
                         "reactive": False, "notifications": False, "auto_simulator": False,
                         "auto_path": "", "lease": 5000}
        for path, assign in [(storage.library, self.load_profiles), (storage.settings, self.load_settings),
                             (storage.mapping, self.load_mapping)]:
            if path.exists():
                try:
                    assign()
                except (OSError, ValueError, RecursionError) as exc:
                    self.history.append(f"Could not read {path.name}: {exc}")
        self.index = next((i for i, p in enumerate(self.profiles) if p.name == profile_name),
                          min(self.settings["index"], len(self.profiles)-1))
        self.auto_simulate = auto_simulate or self.settings["auto_simulator"]
        self.event.connect(self.device_event)
        self.build()
        self.worker = DeviceWorker(backends, self.event.emit)
        self.worker.reconnect = self.settings["reconnect"]
        self.worker.lease_ms = self.settings["lease"]
        self.render_timer = QTimer(self)
        self.render_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.render_timer.timeout.connect(self.render)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save)
        self.metric_timer = QTimer(self)
        self.metric_timer.timeout.connect(self.show_metrics)
        self.metric_timer.start(1000)
        self.refresh_profile()
        self.theme(self.settings["dark"])
        self.setup_tray()

    @property
    def profile(self):
        return self.profiles[self.index]

    def load_profiles(self):
        self.profiles = self.storage.load_profiles()

    def load_settings(self):
        values = read_json(self.storage.settings)
        if not isinstance(values, dict):
            raise ValueError("Invalid settings")
        for key, default in self.settings.items():
            if type(values.get(key)) is type(default):
                self.settings[key] = max(0, values[key]) if key == "index" else values[key]
        self.settings["lease"] = min(60000, max(1000, self.settings["lease"]))
        if len(self.settings["auto_path"]) > 2048:
            self.settings["auto_path"] = ""

    def load_mapping(self):
        self.mapping = validate_mapping(read_json(self.storage.mapping), self.device)

    def build(self):
        main, outer = panel()
        self.setCentralWidget(main)
        header = QHBoxLayout()
        header.addWidget(label("Ducky RGB Studio", "title"))
        header.addStretch()
        self.status = label("Discovering vendor collections…", "detail")
        header.addWidget(self.status)
        self.play_button = button("Pause", self.toggle_play, header)
        self.apply_button = button("Apply to device", self.apply, header)
        self.apply_button.setProperty("primary", True)
        self.apply_button.setEnabled(False)
        self.apply_button.setToolTip("Select the physical Ducky in Devices to change its LEDs.")
        button("Native lighting", self.native, header)
        outer.addLayout(header)

        panes = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(panes)
        left, sidebar = panel()
        left.setMinimumWidth(172)
        sidebar.addWidget(label("DEVICES", "detail"))
        self.device_list = QListWidget()
        self.device_list.currentRowChanged.connect(self.select_device)
        sidebar.addWidget(self.device_list, 1)
        sidebar.addWidget(label("HOST PROFILES", "detail"))
        self.profile_list = QListWidget()
        self.profile_list.currentRowChanged.connect(self.select_profile)
        sidebar.addWidget(self.profile_list, 2)
        profile_actions = QHBoxLayout()
        sidebar.addLayout(profile_actions)
        button("New", self.new_profile, profile_actions)
        button("Manage…", self.profile_menu, profile_actions)
        panes.addWidget(left)

        center, content = panel()
        self.tabs = QTabWidget()
        content.addWidget(self.tabs)
        studio, work = panel()
        self.tabs.addTab(studio, "Studio")
        self.canvas = KeyboardView(self.device)
        self.canvas.selectionChanged.connect(self.selection_changed)
        self.canvas.paintRequested.connect(self.paint_keys)
        self.canvas.inputEvent.connect(self.key_input)
        self.canvas.reactive = self.settings["reactive"]
        work.addWidget(self.canvas, 1)
        tools = QHBoxLayout()
        work.addLayout(tools)
        self.key_group = QComboBox()
        self.key_group.setToolTip("Select predefined key groups, a whole row, or a saved group")
        self.key_group.activated.connect(self.choose_group)
        tools.addWidget(self.key_group)
        button("Invert", lambda: self.canvas.select(self.device.key_ids-self.canvas.selected), tools)
        self.color = "#ff517e"
        self.color_button = button("Paint color…", self.pick_color, tools)
        self.paint_button = button("Brush", self.brush, tools, checkable=True)
        button("Apply", lambda: self.paint_keys(self.canvas.selected), tools)
        button("Clear", self.clear_keys, tools)
        self.mapping_status = label("", "detail")
        work.addWidget(self.mapping_status)
        self.selection_status = label("No keys selected", "detail")
        work.addWidget(self.selection_status)

        settings, settings_box = panel()
        self.tabs.addTab(settings, "Device")
        form = QFormLayout()
        settings_box.addLayout(form)
        self.brightness = number(0, 100, 75, lambda v: self.edit_profile("brightness", v/100), integer=True)
        self.fps = number(1, 60, 30, lambda v: self.edit_profile("fps", v), integer=True)
        self.gamma = number(.2, 4, 1, lambda v: self.edit_profile("gamma", v))
        form.addRow("Global brightness (%)", self.brightness)
        form.addRow("Frame-rate limit", self.fps)
        form.addRow("Output gamma exponent", self.gamma)
        self.fast_box = checkbox(self.settings["fast"], partial(self.setting, "fast"))
        form.addRow("Fast transaction when supported", self.fast_box)
        form.addRow("Reconnect to the same HID path", checkbox(self.settings["reconnect"], partial(self.setting, "reconnect")))
        lease = number(1000, 60000, self.settings["lease"], partial(self.setting, "lease"), integer=True)
        lease.setSingleStep(1000)
        lease.setToolTip("Applies when the next external session opens")
        form.addRow("Session lease (ms)", lease)
        self.auto_device = checkbox(False, self.set_auto_device)
        self.auto_device.setEnabled(False)
        form.addRow("Apply last profile to this device at startup", self.auto_device)
        self.overlay_boxes = []
        for i, name in enumerate(("Caps Lock white", "Z/X/C marker group", "Stock profile CM1", "Stock profile CM2")):
            box = checkbox(False, lambda on, bit=1 << i: self.edit_profile(
                "overlays", self.profile.overlays | bit if on else self.profile.overlays & ~bit))
            box.setToolTip("Stock firmware may replace external colors for this indicator or profile")
            self.overlay_boxes.append(box)
            form.addRow(name, box)
        form.addRow("Dark appearance", checkbox(self.settings["dark"], self.theme))
        form.addRow("Focused reactive input", checkbox(self.settings["reactive"], self.toggle_reactive))
        form.addRow("Minimize to tray", checkbox(self.settings["tray"], partial(self.setting, "tray")))
        form.addRow("Device notifications", checkbox(self.settings["notifications"], partial(self.setting, "notifications")))
        form.addRow("Apply last profile to simulator on startup", checkbox(
            self.settings["auto_simulator"], partial(self.setting, "auto_simulator")))
        if self.startup.available:
            try:
                started = self.startup.enabled()
            except OSError:
                started = False
            form.addRow("Launch at desktop login", checkbox(started, self.register_startup))
        settings_box.addStretch()

        calibration, cal = panel()
        self.tabs.addTab(calibration, "Calibration")
        cal.addWidget(label("Physical LED mapping", "title"))
        cal.addWidget(label("Start a test and select a slot. Switch to Studio to select every key that lights, then return here to record the assignment. A slot can be shared or unused. Record only what you observe."))
        self.slot = number(0, self.device.slots-1, 0, self.update_calibration, integer=True)
        row = QHBoxLayout()
        cal.addLayout(row)
        row.addWidget(label("Firmware slot"))
        row.addWidget(self.slot)
        button("Previous", lambda: self.slot.setValue(self.slot.value()-1), row)
        button("Next", lambda: self.slot.setValue(self.slot.value()+1), row)
        button("Start slot test", self.start_calibration, row)
        button("Stop test", self.stop_test, row)
        row2 = QHBoxLayout()
        cal.addLayout(row2)
        button("Record selected keys", lambda: self.assign(False), row2)
        button("Mark unused", lambda: self.assign(True), row2)
        button("Remove assignment", self.remove_mapping, row2)
        button("Import…", self.import_mapping, row2)
        button("Export…", self.export_mapping, row2)
        self.slot_status = label("", "detail")
        cal.addWidget(self.slot_status)
        cal.addStretch()

        diagnostics, diag = panel()
        self.tabs.addTab(diagnostics, "Diagnostics")
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        diag.addWidget(self.details, 1)
        row = QHBoxLayout()
        diag.addLayout(row)
        for title, color in (("Red", "#ff0000"), ("Green", "#00ff00"), ("Blue", "#0000ff"),
                             ("White", "#ffffff"), ("Off", "#000000")):
            button(title, partial(self.test_color, color), row)
        misc = QHBoxLayout()
        diag.addLayout(misc)
        button("Benchmark", lambda: self.start_timed_test("benchmark"), misc)
        button("Brightness ramp", lambda: self.start_timed_test("ramp"), misc)
        button("Stop / restore", self.stop_test, misc)
        button("Export…", self.report, misc)
        sim = QHBoxLayout()
        diag.addLayout(sim)
        button("Disconnect / reconnect simulator", self.toggle_simulator, sim)
        button("Drop next simulator reply", self.drop_simulator, sim)
        panes.addWidget(center)

        right, edit = panel()
        right.setMinimumWidth(225)
        edit.addWidget(label("EFFECT LIBRARY", "detail"))
        self.effect = QComboBox()
        for identifier, effect in EFFECTS.items():
            self.effect.addItem(f"{effect.category}  /  {effect.label}", identifier)
        edit.addWidget(self.effect)
        button("Add effect layer", self.add_layer, edit)
        edit.addWidget(label("LAYERS  ·  TOP LAYER LAST", "detail"))
        self.layer_list = QListWidget()
        self.layer_list.currentRowChanged.connect(self.show_properties)
        edit.addWidget(self.layer_list, 1)
        actions = (("↑", lambda: self.move(-1)), ("↓", lambda: self.move(1)),
                   ("Duplicate", self.duplicate_layer), ("Delete", self.delete_layer))
        r = QHBoxLayout()
        edit.addLayout(r)
        for text, action in actions:
            button(text, action, r)
        self.properties = QScrollArea()
        self.properties.setWidgetResizable(True)
        edit.addWidget(self.properties, 2)
        panes.addWidget(right)
        panes.setStretchFactor(1, 1)
        panes.setSizes([180, 830, 275])
        for name, shortcut, handler in (
            ("Undo", QKeySequence.StandardKey.Undo, self.undo),
            ("Redo", QKeySequence.StandardKey.Redo, self.redo),
            ("Select all keys", QKeySequence.StandardKey.SelectAll, lambda: self.canvas.select(self.device.key_ids)),
        ):
            action = QAction(name, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(handler)
            self.addAction(action)
        self.update_calibration()

    def setting(self, name, value):
        self.settings[name] = value
        if hasattr(self, "worker") and name == "reconnect":
            self.worker.reconnect = value
        if hasattr(self, "worker") and name == "lease":
            self.worker.lease_ms = value
        if hasattr(self, "save_timer"):
            self.save_timer.start(350)
            self.render()

    def theme(self, on):
        self.setStyleSheet(DARK if on else LIGHT)
        self.canvas.dark = on
        self.canvas.update()
        if hasattr(self, "save_timer"):
            self.setting("dark", on)

    def set_auto_device(self, on):
        if self.endpoint and not self.endpoint.simulator and self.caps:
            self.setting("auto_path", self.endpoint.path.hex() if on else "")

    def register_startup(self, on):
        try:
            self.startup.set(on)
        except (OSError, ValueError) as exc:
            self.notice(f"Startup registration failed: {exc}")

    def toggle_reactive(self, on):
        self.canvas.reactive = on
        self.records.clear()
        self.setting("reactive", on)

    def key_input(self, key, down):
        if key not in self.device.key_ids:
            return
        _, _, count = self.records.get(key, (0, False, 0))
        self.records[key] = (time.monotonic(), down, min(10, count+int(down)))
        self.render()

    def refresh_profile(self):
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        self.profile_list.addItems([p.name for p in self.profiles])
        self.profile_list.setCurrentRow(self.index)
        self.profile_list.blockSignals(False)
        self.groups()
        self.refresh_layers(0)
        self.sync_controls()
        self.refresh_mapping()
        self.changed()

    def sync_controls(self):
        pairs = [(self.brightness, round(self.profile.brightness*100)), (self.fps, self.profile.fps),
                 (self.gamma, self.profile.gamma)]
        for control, value in pairs:
            control.blockSignals(True)
            control.setValue(value)
            control.blockSignals(False)
        for i, box in enumerate(self.overlay_boxes):
            box.blockSignals(True)
            box.setChecked(bool(self.profile.overlays & 1 << i))
            box.setEnabled(bool(self.caps and self.caps.supported_overlays & 1 << i))
            box.blockSignals(False)
        self.fast_box.setEnabled(self.caps is None or bool(self.caps.features & 4))
        physical = bool(self.endpoint and not self.endpoint.simulator and self.caps)
        self.auto_device.setEnabled(physical)
        self.auto_device.blockSignals(True)
        self.auto_device.setChecked(bool(physical and self.endpoint.path.hex() == self.settings["auto_path"]))
        self.auto_device.blockSignals(False)

    def select_profile(self, index):
        if index != self.index and 0 <= index < len(self.profiles):
            self.index = index
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.refresh_profile()

    def new_profile(self):
        name, ok = QInputDialog.getText(self, "New host profile", "Name")
        if ok and name.strip():
            self.add_profile(Profile(name.strip()[:80], layers=[]))

    def add_profile(self, profile):
        if len(self.profiles) >= 128:
            self.notice("Profile library is full.")
            return
        self.profiles.append(profile)
        self.select_profile(len(self.profiles)-1)
        self.rebuild_tray()

    def add_builtin_profile(self, profile):
        profile = deepcopy(profile)
        names = {item.name.casefold() for item in self.profiles}
        base = profile.name
        suffix = 2
        while profile.name.casefold() in names:
            profile.name = f"{base} ({suffix})"
            suffix += 1
        self.add_profile(profile)

    def profile_menu(self):
        menu = QMenu(self)
        presets = menu.addMenu("Add built-in profile")
        for profile in examples():
            action = presets.addAction(profile.name, partial(self.add_builtin_profile, profile))
            action.setToolTip(profile.description)
        presets.setToolTipsVisible(True)
        for title, handler in (("Rename…", self.rename), ("Edit description…", self.describe),
                               ("Duplicate", self.duplicate_profile), ("Delete", self.delete_profile),
                               ("Import JSON…", self.import_profile), ("Export JSON…", self.export_profile)):
            menu.addAction(title, handler)
        menu.exec(self.profile_list.mapToGlobal(self.profile_list.rect().bottomLeft()))

    def rename(self):
        name, ok = QInputDialog.getText(self, "Rename profile", "Name", text=self.profile.name)
        if ok and name.strip():
            self.edit_profile("name", name.strip()[:80])
            self.refresh_profile()
            self.rebuild_tray()

    def describe(self):
        result, ok = QInputDialog.getMultiLineText(self, "Profile description", "Description", self.profile.description)
        if ok:
            self.edit_profile("description", result[:1500])

    def duplicate_profile(self):
        profile = deepcopy(self.profile)
        profile.name = (profile.name[:74]+" copy")
        self.add_profile(profile)

    def delete_profile(self):
        if len(self.profiles) == 1:
            self.notice("Keep at least one profile.")
        elif QMessageBox.question(self, "Delete profile?", f"Delete {self.profile.name}?") == QMessageBox.StandardButton.Yes:
            del self.profiles[self.index]
            self.index = min(self.index, len(self.profiles)-1)
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.refresh_profile()
            self.rebuild_tray()

    def read_dialog(self, title, callback):
        from pathlib import Path
        path, _ = QFileDialog.getOpenFileName(self, title, "", "JSON (*.json)")
        if path:
            try:
                callback(read_json(Path(path)))
            except (ValueError, OSError, RecursionError) as exc:
                self.notice(f"Import failed: {exc}")

    def write_dialog(self, title, name, data):
        from pathlib import Path
        path, _ = QFileDialog.getSaveFileName(self, title, name, "JSON (*.json)")
        if path:
            try:
                write_json(Path(path), data)
            except (ValueError, OSError) as exc:
                self.notice(f"Export failed: {exc}")

    def import_profile(self):
        self.read_dialog("Import a host profile", lambda data: self.add_profile(validate_profile(data)))

    def export_profile(self):
        self.write_dialog("Export host profile", "lighting-profile.json", self.profile.encode())

    def snapshot(self):
        self.undo_stack.append(deepcopy(self.profile))
        self.undo_stack = self.undo_stack[-60:]
        self.redo_stack.clear()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(deepcopy(self.profile))
            self.profiles[self.index] = self.undo_stack.pop()
            self.refresh_profile()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(deepcopy(self.profile))
            self.profiles[self.index] = self.redo_stack.pop()
            self.refresh_profile()

    def edit_profile(self, field, value):
        if getattr(self.profile, field) != value:
            self.snapshot()
            setattr(self.profile, field, value)
            self.changed()

    def changed(self):
        if not hasattr(self, "render_timer"):
            return
        self.save_timer.start(350)
        if self.playing and (self.test_until or any(
            layer.enabled and EFFECTS[layer.effect].category != "Static"
            for layer in self.profile.layers)):
            interval = max(1, round(1000/self.profile.fps))
            if not self.render_timer.isActive() or self.render_timer.interval() != interval:
                self.render_timer.start(interval)
        else:
            self.render_timer.stop()
        self.render()

    def save(self):
        try:
            self.storage.save_profiles(self.profiles)
            write_json(self.storage.settings, {**self.settings, "index": self.index})
        except OSError as exc:
            self.notice(f"Autosave failed: {exc}")

    def groups(self):
        self.group_values = [None, self.device.key_ids]
        self.key_group.clear()
        self.key_group.addItems(["Select keys…", "All keys"])
        for name, ids in {**GROUPS, **self.profile.groups}.items():
            self.key_group.addItem(name)
            self.group_values.append(ids)
        for row in sorted({key.y for key in self.device.keys}):
            self.key_group.addItem(f"Row {row+1}")
            self.group_values.append({key.id for key in self.device.keys if key.y == row})
        self.key_group.addItem("Save current selection as group…")
        self.group_values.append(None)

    def choose_group(self, i):
        if i == len(self.group_values)-1 and self.canvas.selected:
            name, ok = QInputDialog.getText(self, "Save key group", "Name")
            if ok and name.strip() and len(self.profile.groups) < 32:
                self.edit_profile("groups", {**self.profile.groups, name.strip()[:40]: sorted(self.canvas.selected)})
                self.groups()
        elif self.group_values[i] is not None:
            self.canvas.select(self.group_values[i])

    def selection_changed(self, selection):
        self.selection_status.setText(f"{len(selection)} selected · {len(selection & self.canvas.mapped)} mapped")

    def refresh_layers(self, selected=None):
        if selected is None:
            selected = self.layer_list.currentRow()
        self.layer_list.blockSignals(True)
        self.layer_list.clear()
        self.layer_list.addItems([("●  " if l.enabled else "○  ")+l.name for l in self.profile.layers])
        self.layer_list.setCurrentRow(min(selected, len(self.profile.layers)-1))
        self.layer_list.blockSignals(False)
        self.show_properties(self.layer_list.currentRow())

    def show_properties(self, index):
        if 0 <= index < len(self.profile.layers):
            layer = self.profile.layers[index]
            def edit(field, value, refresh=False):
                if (index < len(self.profile.layers) and self.profile.layers[index] is layer):
                    self.layer_edit(index, field, value, refresh)
            editor = LayerEditor(layer, edit, lambda: sorted(self.canvas.selected), self.notice)
            self.properties.setWidget(editor)
        else:
            body, box = panel()
            box.addWidget(label("Add an effect to edit its properties.", "detail"))
            self.properties.setWidget(body)

    def layer_edit(self, i, field, value, refresh=False):
        layer = self.profile.layers[i]
        if getattr(layer, field) != value:
            self.snapshot()
            setattr(layer, field, value)
            if refresh:
                # Defer rebuilding while the Qt editor signal is on the stack.
                QTimer.singleShot(0, lambda: self.refresh_layers(i))
            self.changed()

    def add_layer(self):
        if len(self.profile.layers) < 32:
            self.snapshot()
            effect = self.effect.currentData()
            blend = "Screen" if EFFECTS[effect].category == "Reactive" else "Normal"
            self.profile.layers.append(Layer(effect, EFFECTS[effect].label, speed=.35, blend=blend))
            self.refresh_layers(len(self.profile.layers)-1)
            self.changed()

    def duplicate_layer(self):
        i = self.layer_list.currentRow()
        if i >= 0 and len(self.profile.layers) < 32:
            self.snapshot()
            duplicate = deepcopy(self.profile.layers[i])
            duplicate.name = duplicate.name[:74]+" copy"
            self.profile.layers.insert(i+1, duplicate)
            self.refresh_layers(i+1)
            self.changed()

    def delete_layer(self):
        i = self.layer_list.currentRow()
        if i >= 0:
            self.snapshot()
            del self.profile.layers[i]
            self.refresh_layers(i)
            self.changed()

    def move(self, delta):
        i = self.layer_list.currentRow()
        if i >= 0 and 0 <= i+delta < len(self.profile.layers):
            self.snapshot()
            self.profile.layers[i], self.profile.layers[i+delta] = self.profile.layers[i+delta], self.profile.layers[i]
            self.refresh_layers(i+delta)
            self.changed()

    def pick_color(self):
        color = QColorDialog.getColor(QColor(self.color), self, "Brush color")
        if color.isValid():
            self.color = color.name()
            self.color_button.setText(self.color+"…")

    def brush(self, enabled):
        self.canvas.painting = enabled

    def paint_keys(self, keys):
        if not keys or self.calibration:
            return
        if len(self.profile.layers) == 32 and not any(l.effect == "paint" for l in self.profile.layers):
            self.notice("Remove a layer before adding a paint layer.")
            return
        self.snapshot()
        i = next((i for i in range(len(self.profile.layers)-1, -1, -1)
                  if self.profile.layers[i].effect == "paint"), None)
        if i is None:
            i = len(self.profile.layers)
            self.profile.layers.append(Layer("paint", "Per-key paint"))
        self.profile.layers[i].paint.update({key: self.color for key in keys})
        self.refresh_layers(i)
        self.changed()

    def clear_keys(self):
        selected = self.canvas.selected
        if selected and any(selected & layer.paint.keys() for layer in self.profile.layers):
            self.snapshot()
            for layer in self.profile.layers:
                layer.paint = {k: v for k, v in layer.paint.items() if k not in selected}
            self.changed()

    def refresh_mapping(self):
        self.renderer = Renderer(self.device, self.mapping)
        self.canvas.mapped = {key for assignment in self.mapping.values() if assignment.verified
                              for key in assignment.keys}
        self.mapping_status.setText(f"{sum(row.verified for row in self.mapping.values())}/{self.device.slots} LED slots verified. "
                                    "Unmapped per-key edits appear in preview only.")
        self.selection_changed(self.canvas.selected)

    def update_calibration(self, *_):
        slot = self.slot.value()
        assignment = self.mapping.get(slot)
        if assignment:
            detail = (", ".join(assignment.keys) or "Unused") + (" · verified" if assignment.verified else " · provisional")
        else:
            detail = "Unassigned"
        self.slot_status.setText(f"Bank {slot//self.device.slots_per_bank} · Index {slot%self.device.slots_per_bank} · {detail}")
        if self.calibration:
            self.canvas.highlight = set(assignment.keys) if assignment else set()
            self.canvas.select(self.canvas.highlight)
            frame = bytearray(self.device.slots*3)
            frame[slot*3:slot*3+3] = bytes((255, 32, 16))
            self.override = Output(bytes(frame), 24000, 0, False)
            self.render()

    def start_calibration(self):
        if self.endpoint is None or self.caps is None:
            self.notice("Negotiate a compatible device or the simulator first.")
            return
        self.begin_test()
        self.calibration = self.canvas.calibrating = True
        self.paint_button.setChecked(False)
        self.update_calibration()
        self.worker.select(self.endpoint, enabled=True)

    def assign(self, unused):
        if not self.calibration:
            self.notice("Start a slot test first.")
            return
        if not self.endpoint.simulator and (self.caps is None or self.last_displayed_output != self.override):
            self.notice("Wait for the device to acknowledge the active slot test.")
            return
        keys = () if unused else tuple(sorted(self.canvas.selected))
        if not keys and not unused:
            self.notice("Select observed keys in Studio before recording.")
            return
        self.mapping[self.slot.value()] = Assignment(keys, not self.endpoint.simulator)
        self.save_mapping()

    def save_mapping(self):
        try:
            write_json(self.storage.mapping, mapping_json(self.mapping, self.device))
        except OSError as exc:
            self.notice(f"Could not save mapping: {exc}")
        self.refresh_mapping()
        self.update_calibration()
        self.render()

    def remove_mapping(self):
        self.mapping.pop(self.slot.value(), None)
        self.save_mapping()

    def import_mapping(self):
        def assign(mapping):
            self.mapping = validate_mapping(mapping, self.device)
            self.save_mapping()
        self.read_dialog("Import LED map", assign)

    def export_mapping(self):
        self.write_dialog("Export LED map", "ducky-one3-sf-map.json", mapping_json(self.mapping, self.device))

    def render(self):
        if not hasattr(self, "renderer") or not hasattr(self, "worker"):
            return
        now = time.monotonic()
        t = now-self.tick_origin if self.playing else self.frozen
        if self.test_until:
            start, end, mode = self.test_until
            if now >= end:
                if mode == "benchmark":
                    start_at, before, fast = self.benchmark_base
                    duration = now-start_at
                    self.benchmark_result = (f"{'Fast preferred' if fast else 'Standard'} benchmark · "
                        f"{(self.metrics.accepted-before.accepted)/duration:.1f} accepted/s · "
                        f"{(self.metrics.displayed-before.displayed)/duration:.1f} scanout acknowledgments/s")
                    self.notice(self.benchmark_result)
                self.stop_test()
                return
            if mode == "benchmark":
                value = int((now-start)*self.profile.fps) % 2
                self.override = Output(bytes([255*value, 30, 255*(1-value)]) * self.device.slots,
                                       24000, 0, self.settings["fast"])
            else:
                self.override = Output(bytes([255, 255, 255])*self.device.slots, round(65535*(now-start)/(end-start)),
                                       0, self.settings["fast"])
        events = [(key, now-stamp, down, count) for key, (stamp, down, count) in self.records.items()]
        profile = self.profile
        colors, data = self.renderer.render(profile.layers, t, events, gamma=profile.gamma,
                                            preview_brightness=profile.brightness)
        self.canvas.colors = colors
        self.canvas.update()
        self.rendered += 1
        if self.external or self.override:
            self.worker.submit(self.override or Output(data, round(profile.brightness*65535),
                                                       profile.overlays, self.settings["fast"]))

    def toggle_play(self):
        if self.playing:
            self.frozen = time.monotonic()-self.tick_origin
            self.play_button.setText("Play")
        else:
            self.tick_origin = time.monotonic()-self.frozen
            self.play_button.setText("Pause")
        self.playing = not self.playing
        self.changed()

    def select_device(self, index):
        if not hasattr(self, "worker"):
            return
        endpoint = self.discovered[index] if 0 <= index < len(self.discovered) else None
        if endpoint != self.endpoint:
            self.native()
            self.endpoint, self.caps, self.last_displayed_output = endpoint, None, None
            self.worker.select(endpoint)
            self.apply_button.setEnabled(False)
            self.apply_button.setText("Apply to simulator" if endpoint and endpoint.simulator else "Apply to keyboard")
            self.sync_controls()

    def apply(self):
        if self.endpoint is not None and self.caps is not None:
            if self.endpoint.simulator:
                self.notice("Simulator only. Select the physical Ducky in Devices to change its LEDs.")
            self.external = True
            self.render()
            self.worker.select(self.endpoint, enabled=True)

    def native(self):
        self.external = False
        self.override = None
        self.test_until = None
        self.calibration = self.canvas.calibrating = False
        if hasattr(self, "worker"):
            self.worker.select(self.endpoint)
            self.changed()

    def begin_test(self):
        self.test_until = None
        self.calibration = self.canvas.calibrating = False

    def start_timed_test(self, mode):
        if self.caps is None:
            self.notice("Negotiate firmware before running a test.")
            return
        self.begin_test()
        now = time.monotonic()
        self.test_until = (now, now+8, mode)
        self.benchmark_base = (now, self.metrics, self.settings["fast"])
        self.playing = True
        self.play_button.setText("Pause")
        self.changed()
        self.worker.select(self.endpoint, enabled=True)

    def test_color(self, color):
        if self.caps is None:
            self.notice("Negotiate firmware before running a test.")
            return
        self.begin_test()
        self.override = Output(bytes.fromhex(color[1:])*self.device.slots, 24000)
        self.render()
        self.worker.select(self.endpoint, enabled=True)

    def stop_test(self):
        self.override = self.test_until = None
        self.calibration = self.canvas.calibrating = False
        self.worker.select(self.endpoint, enabled=self.external)
        self.changed()

    def toggle_simulator(self):
        self.backends[True].device.online = not self.backends[True].device.online

    def drop_simulator(self):
        self.backends[True].drop_next += 1

    def notice(self, message):
        self.history.append(message)
        self.statusBar().showMessage(message, 6000)

    def device_event(self, topic, value):
        if topic == "devices":
            self.discovered = value
            self.device_list.blockSignals(True)
            self.device_list.clear()
            self.device_list.addItems([d.label if d.simulator else f"{d.label}  ·  HID {i+1}"
                                       for i, d in enumerate(value)])
            if self.endpoint in value:
                self.device_list.setCurrentRow(value.index(self.endpoint))
            self.device_list.blockSignals(False)
            physical = [endpoint for endpoint in value if not endpoint.simulator]
            if (self.settings["auto_path"] and not self.auto_simulate and self.endpoint is None and
                    len(physical) == 1 and physical[0].path.hex() == self.settings["auto_path"]):
                self._auto_apply = physical[0]
                self.device_list.setCurrentRow(value.index(physical[0]))
            if not physical and self.endpoint is None and not self.auto_simulate:
                self.status.setText("No accessible USB keyboard selected")
            if self.auto_simulate and SIMULATOR in value:
                self.auto_simulate = False
                self.device_list.setCurrentRow(value.index(SIMULATOR))
        elif topic == "caps":
            endpoint, caps = value
            if endpoint != self.endpoint:
                return
            self.caps = caps
            self.apply_button.setEnabled(True)
            self.sync_controls()
            if ((endpoint.simulator and self.settings["auto_simulator"])
                    or getattr(self, "_auto_apply", None) == endpoint):
                self._auto_apply = None
                self.apply()
        elif topic == "displayed":
            endpoint, output = value
            if endpoint == self.endpoint:
                self.last_displayed_output = output
        elif topic == "metrics":
            self.metrics = value
        elif topic == "status":
            if self.endpoint and self.endpoint.simulator:
                value = "Simulator • " + value
            if self.status.text() != value:
                self.status.setText(value)
                self.history.append(value)
                tray = getattr(self, "tray", None)
                if tray and self.settings["notifications"] and value.startswith(("Connected", "Disconnected")):
                    tray.showMessage("Ducky RGB Studio", value)
        elif topic == "notice":
            self.notice(value)

    def show_metrics(self):
        now = time.monotonic()
        prev, rendered, last = self.previous_stats
        dt = max(.001, now-prev)
        self.previous_stats = (now, self.rendered, self.metrics)
        caps = self.caps
        e = self.endpoint
        readout = [
            f"Platform  {platform.system()}",
            f"Device  {e.label if e else 'None'}",
            f"Transport  {'Simulator' if e.simulator else e.backend} · {e.vid:04x}:{e.pid:04x} · interface {e.interface}"
            if e else "Transport  No connection",
            f"Protocol  V4 major 1 · layout {caps.layout:08x} · flags 0x{caps.features:02x}" if caps else "Protocol  Unknown",
            f"Rendering  {(self.rendered-rendered)/dt:.1f} FPS",
            f"Reports  {(self.metrics.submitted-last.submitted)/dt:.1f} submitted frames/s · "
            f"{(self.metrics.accepted-last.accepted)/dt:.1f} accepted/s · "
            f"{(self.metrics.displayed-last.displayed)/dt:.1f} scanout acknowledgments/s",
            f"Last transaction + scanout  {self.metrics.latency_ms:.1f} ms",
            f"Totals  {self.metrics.accepted} accepted · {self.metrics.dropped} coalesced · {self.metrics.timeouts} attempt timeouts · {self.metrics.retries} retries",
            f"Settings  brightness {self.profile.brightness:.0%} · overlays 0x{self.profile.overlays:x} · "
            f"{'fast preferred' if self.settings['fast'] else 'standard'}",
            "",
            *[f"{name}  {info.description}" for name, info in capability_report().items()],
            "", *([self.benchmark_result] if self.benchmark_result else []), *list(self.history)[-10:],
        ]
        self.details.setPlainText("\n".join(readout))

    def report(self):
        self.write_dialog("Export diagnostics", "ducky-diagnostics.json",
                          {"version": 1, "os": platform.system(), "model": self.device.id,
                           "simulator": bool(self.endpoint and self.endpoint.simulator),
                           "metrics": asdict(self.metrics),
                           "protocol": {"features": self.caps.features, "layout": self.caps.layout} if self.caps else None})

    def setup_tray(self):
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
            self.tray = QSystemTrayIcon(icon, self)
            self.tray.activated.connect(lambda reason: self.showNormal()
                                        if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
            self.rebuild_tray()
            self.tray.show()

    def rebuild_tray(self):
        if getattr(self, "tray", None) is not None:
            old = self.tray.contextMenu()
            menu = QMenu(self)
            menu.addAction("Show studio", self.showNormal)
            menu.addAction("Pause / play", self.toggle_play)
            menu.addAction("Restore native lighting", self.native)
            profiles = menu.addMenu("Profiles")
            for i, profile in enumerate(self.profiles):
                profiles.addAction(profile.name, partial(self.select_profile, i))
            menu.addAction("Quit", self.quit)
            self.tray.setContextMenu(menu)
            if old:
                old.deleteLater()

    def quit(self):
        self.force_close = True
        self.close()

    def closeEvent(self, event):
        if self.settings["tray"] and self.tray and self.tray.isVisible() and not getattr(self, "force_close", False):
            self.hide()
            event.ignore()
            return
        self.render_timer.stop()
        self.metric_timer.stop()
        self.save_timer.stop()
        self.save()
        self.status.setText("Restoring native lighting…")
        if self.tray:
            self.tray.hide()
        if not self.worker.close():
            self.notice("Native restoration unconfirmed. The firmware lease will expire.")
        event.accept()
