"""Declarative layer property editor with model-agnostic commit callbacks."""
from functools import partial

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QComboBox, QFormLayout, QHBoxLayout, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from .effects import EFFECTS
from .engine import BLENDS
from .widgets import button, checkbox, label, number


class LayerEditor(QWidget):
    def __init__(self, layer, edit, key_selection, notice):
        super().__init__()
        self.layer, self.edit, self.notice = layer, edit, notice
        box = QVBoxLayout(self)
        box.addWidget(label(EFFECTS[layer.effect].label, "detail"))
        form = QFormLayout()
        box.addLayout(form)
        name = QLineEdit(layer.name)
        name.setMaxLength(80)
        name.editingFinished.connect(lambda: edit("name", name.text().strip() or layer.name, True))
        form.addRow("Name", name)
        form.addRow("Enabled", checkbox(layer.enabled, lambda value: edit("enabled", value, True)))
        mix = QComboBox()
        mix.addItems(BLENDS)
        mix.setCurrentText(layer.blend)
        mix.currentTextChanged.connect(lambda value: edit("blend", value))
        form.addRow("Blend", mix)
        for key, caption, maximum in (("opacity", "Opacity", 1), ("brightness", "Brightness", 1),
                                      ("speed", "Speed", 8), ("phase", "Phase", 60)):
            form.addRow(caption, number(0, maximum, getattr(layer, key),
                        lambda value, field=key: edit(field, value)))
        for param in EFFECTS[layer.effect].parameters:
            value = layer.settings()[param.name]
            if param.kind == "palette":
                self.palette_row(form, param, value)
                continue
            if param.kind == "stops":
                control = QLineEdit(" ".join(map(str, value)))
                control.setMaxLength(128)
                control.editingFinished.connect(partial(self.update_stops, param, control))
            elif param.kind == "color":
                control = QPushButton(value)
                control.clicked.connect(lambda _=False, p=param, c=control: self.edit_color(p, c))
            elif param.kind == "boolean":
                control = checkbox(value, partial(self.parameter, param))
            else:
                control = number(param.minimum, param.maximum, value, partial(self.parameter, param),
                                 integer=param.kind == "integer")
            control.setToolTip(param.description)
            form.addRow(param.name, control)
        button(f"Use selection as mask ({len(layer.mask)})", lambda: edit("mask", key_selection(), True), box)
        button("Clear layer mask", lambda: edit("mask", [], True), box)
        box.addStretch()

    def palette_row(self, form, param, palette):
        control = QLineEdit(" ".join(palette))
        control.setMaxLength(127)
        control.setToolTip("Hex RGB colors in gradient order. Example #ff0000 #00ff00")
        control.editingFinished.connect(partial(self.update_palette, param, control))
        form.addRow(param.name, control)
        swatches = QHBoxLayout()
        swatches.setSpacing(3)
        for index, color in enumerate(palette[:8]):
            chip = button(" ", partial(self.pick_swatch, param, index, control), swatches)
            chip.setAccessibleName(f"Edit palette color {index+1}")
            chip.setToolTip(f"Edit color {index+1}: {color}")
            chip.setFixedWidth(21)
            chip.setStyleSheet(f"background: {color}")
        form.addRow("", swatches)

    def update_palette(self, param, control):
        try:
            value = param.validate(control.text().split())
            if list(self.layer.settings()[param.name]) != value:
                self.parameter(param, value, refresh=True)
        except ValueError as exc:
            self.notice(str(exc))
            control.setText(" ".join(self.layer.settings()[param.name]))

    def edit_color(self, param, control):
        color = QColorDialog.getColor(QColor(control.text()), self, param.name)
        if color.isValid():
            control.setText(color.name())
            self.parameter(param, color.name())

    def pick_swatch(self, param, index, control):
        colors = list(self.layer.settings()[param.name])
        if index < len(colors):
            color = QColorDialog.getColor(QColor(colors[index]), self, f"Palette color {index+1}")
            if color.isValid():
                colors[index] = color.name()
                control.setText(" ".join(colors))
                self.parameter(param, colors, refresh=True)

    def update_stops(self, param, control):
        try:
            values = [float(part) for part in control.text().split()]
            if values and len(values) != len(self.layer.settings()["Palette"]):
                raise ValueError("Supply one position per palette color")
            self.parameter(param, values)
        except ValueError as exc:
            self.notice(str(exc))
            control.setText(" ".join(map(str, self.layer.settings()[param.name])))

    def parameter(self, definition, value, *, refresh=False):
        value = definition.validate(value)
        params = {**self.layer.params, definition.name: value}
        if definition.name == "Palette" and params.get("Stop positions") and len(params["Stop positions"]) != len(value):
            params.pop("Stop positions")
            self.notice("Palette length changed. Stops are now evenly spaced.")
        self.edit("params", params, refresh)
