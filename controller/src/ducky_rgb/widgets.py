"""Shared Qt controls and studio themes."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDoubleSpinBox, QLabel, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

DARK = """
QWidget { background: #161b27; color: #e4eaf6; font-size: 13px; }
QLabel[role="title"] { font-size: 24px; font-weight: 700; color: #f1f7ff; }
QLabel[role="detail"] { color: #aebbd0; }
QPushButton, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QListWidget, QTextEdit {
  background: #232b3b; border: 1px solid #3a455a; border-radius: 5px; padding: 5px;
}
QPushButton:hover { background: #33435a; }
QPushButton:checked, QPushButton[primary="true"] { background: #366663; color: #ffffff; }
QPushButton:disabled { color: #8492a6; }
QListWidget::item { padding: 5px; }
QListWidget::item:selected { background: #3a5269; }
QTabBar::tab { background: #252d3e; padding: 8px 13px; }
QTabBar::tab:selected { background: #385671; }
QSplitter::handle { background: #333e50; width: 3px; }
"""


LIGHT = """
QWidget { background: #f2f5fa; color: #17253b; font-size: 13px; }
QLabel[role="title"] { font-size: 24px; font-weight: 700; color: #142135; }
QLabel[role="detail"] { color: #415571; }
QPushButton, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QListWidget, QTextEdit {
  background: #ffffff; border: 1px solid #aab8cd; border-radius: 5px; padding: 5px;
}
QPushButton:hover { background: #dce9f3; }
QPushButton:checked, QPushButton[primary="true"] { background: #d2efeb; }
QPushButton:disabled { color: #68778b; }
QListWidget::item { padding: 5px; }
QListWidget::item:selected { background: #cbdff3; color: #17253b; }
QTabBar::tab { background: #e6ecf4; padding: 8px 13px; }
QTabBar::tab:selected { background: #cbdff3; }
QSplitter::handle { background: #b9c6d8; width: 3px; }
"""


def panel():
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(9, 9, 9, 9)
    layout.setSpacing(8)
    return widget, layout


def label(text, role=None):
    item = QLabel(text)
    item.setWordWrap(True)
    item.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        item.setProperty("role", role)
    return item


def button(text, action, layout, *, checkable=False):
    item = QPushButton(text)
    item.setCheckable(checkable)
    item.clicked.connect(action)
    layout.addWidget(item)
    return item


def number(minimum, maximum, value, change, *, integer=False):
    control = QSpinBox() if integer else QDoubleSpinBox()
    control.setRange(minimum, maximum)
    if not integer:
        control.setSingleStep(.1)
        control.setDecimals(2)
    control.setValue(value)
    control.valueChanged.connect(change)
    control.setKeyboardTracking(False)
    return control

def checkbox(checked, handler):
    item = QCheckBox()
    item.setChecked(checked)
    item.toggled.connect(handler)
    return item
