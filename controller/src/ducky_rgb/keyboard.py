"""High-DPI physical keyboard canvas, selection and paint gestures."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .devices import DUCKY


class KeyboardView(QWidget):
    selectionChanged = Signal(object)
    paintRequested = Signal(object)
    inputEvent = Signal(str, bool)

    def __init__(self, device=DUCKY):
        super().__init__()
        self.device = device
        self.colors = {}
        self.selected = set()
        self.mapped = set()
        self.highlight = set()
        self.calibrating = False
        self.dark = True
        self.pressed = set()
        self.painting = False
        self.reactive = False
        self.zoom = 1.0
        self.anchor = self.cursor = None
        self.stroke = set()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(240)
        self.setToolTip("Click to select. Shift selects a range. Ctrl or Command toggles. Drag to box-select.")

    def geometry_for_keys(self):
        width = max(k.x+k.width for k in self.device.keys)
        height = 1+max(k.y for k in self.device.keys)
        scale = max(1, min((self.width()-34)/width, (self.height()-30)/height)*self.zoom)
        origin_x = (self.width()-width*scale)/2
        origin_y = (self.height()-height*scale)/2
        return {key.id: QRectF(origin_x+key.x*scale+2, origin_y+key.y*scale+2,
                               max(1, key.width*scale-4), max(1, scale-4))
                for key in self.device.keys}

    def select(self, keys):
        self.selected = set(keys) & self.device.key_ids
        self.selectionChanged.emit(set(self.selected))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#10141e" if self.dark else "#dee7f2"))
        for key, rect in zip(self.device.keys, self.geometry_for_keys().values()):
            color = QColor(*self.colors.get(key.id, (36, 44, 58)))
            if self.calibrating:
                color = QColor("#55d6ba" if key.id in self.highlight else "#242c3a")
            outline = QColor("#f1d78c") if key.id in self.selected else QColor("#47556b")
            painter.setPen(QPen(outline, 2 if key.id in self.selected else 1))
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 6, 6)
            light = color.red()*.2126+color.green()*.7152+color.blue()*.0722
            painter.setPen(QColor("#10141e" if light > 140 else "#eff4ff"))
            font = QFont(self.font())
            font.setPixelSize(max(8, min(15, int(rect.height()*.31))))
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, key.label)
            if key.id in self.mapped:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#6aefb7"))
                painter.drawEllipse(rect.topLeft()+QPointF(7, 7), 2, 2)
        if self.anchor is not None and self.cursor is not None and not self.painting:
            box = QRectF(self.anchor, self.cursor).normalized()
            if box.width()+box.height() > 5:
                painter.setPen(QPen(QColor("#8be7e5"), 1))
                painter.setBrush(QColor(110, 227, 220, 45))
                painter.drawRect(box)

    def key_at(self, point):
        return next((key for key, rect in self.geometry_for_keys().items() if rect.contains(point)), None)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self.anchor = self.cursor = event.position()
            self.stroke = set()
            if self.painting:
                key = self.key_at(self.anchor)
                if key:
                    self.stroke.add(key)

    def mouseMoveEvent(self, event):
        if self.anchor is not None:
            self.cursor = event.position()
            if self.painting:
                key = self.key_at(self.cursor)
                if key:
                    self.stroke.add(key)
                    self.select(self.stroke)
            self.update()

    def mouseReleaseEvent(self, event):
        if self.anchor is None or event.button() != Qt.MouseButton.LeftButton:
            return
        end = event.position()
        box = QRectF(self.anchor, end).normalized()
        point = self.key_at(end)
        modifiers = event.modifiers()
        toggle = modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)
        extend = modifiers & Qt.KeyboardModifier.ShiftModifier
        if self.painting:
            if point:
                self.stroke.add(point)
            if self.stroke:
                self.select(self.stroke)
                self.paintRequested.emit(set(self.stroke))
        else:
            if box.width()+box.height() > 6:
                keys = {key for key, rect in self.geometry_for_keys().items() if box.intersects(rect)}
            elif extend and point and getattr(self, "last_key", None):
                order = [key.id for key in self.device.keys]
                index = sorted((order.index(point), order.index(self.last_key)))
                keys = set(order[index[0]:index[1]+1])
            else:
                keys = {point} if point else set()
            if point:
                self.last_key = point
            self.select(self.selected ^ keys if toggle else self.selected | keys if extend else keys)
        self.anchor = self.cursor = None
        self.update()

    def wheelEvent(self, event):
        if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            self.zoom = max(.65, min(1.15, self.zoom+(.05 if event.angleDelta().y() > 0 else -.05)))
            self.update()
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        self.emit_key(event, True)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        self.emit_key(event, False)
        super().keyReleaseEvent(event)

    def emit_key(self, event, down):
        if not self.reactive or event.isAutoRepeat():
            return
        keys = Qt.Key
        aliases = {keys.Key_Space: "Space", keys.Key_Up: "Up", keys.Key_Down: "Down",
                   keys.Key_Left: "Left", keys.Key_Right: "Right", keys.Key_Escape: "Esc",
                   keys.Key_Return: "Enter", keys.Key_Backspace: "Backspace", keys.Key_Tab: "Tab"}
        key = aliases.get(event.key())
        if key is None and (32 < event.key() < 127):
            key = chr(event.key()).upper()
        if key in self.device.key_ids:
            if down:
                self.pressed.add(key)
            else:
                self.pressed.discard(key)
            self.inputEvent.emit(key, down)

    def focusOutEvent(self, event):
        for key in self.pressed:
            self.inputEvent.emit(key, False)
        self.pressed.clear()
        super().focusOutEvent(event)
