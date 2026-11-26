"""Device definitions, physical geometry and user-observed slot assignments."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Key:
    id: str
    label: str
    x: float
    y: int
    width: float


@dataclass(frozen=True)
class Device:
    id: str
    title: str
    keys: tuple[Key, ...]
    banks: int
    slots_per_bank: int
    wire_layout: int

    @property
    def slots(self):
        return self.banks * self.slots_per_bank

    @property
    def key_ids(self):
        return frozenset(key.id for key in self.keys)


def ansi_keys():
    rows = (
        [("Esc", 1), *[(c, 1) for c in "1234567890-="], ("Backspace", 2), (None, .25), ("Delete", 1)],
        [("Tab", 1.5), *[(c, 1) for c in "QWERTYUIOP[]"], ("\\", 1.5), (None, .25), ("Page Up", 1)],
        [("Caps Lock", 1.75), *[(c, 1) for c in "ASDFGHJKL;'"], ("Enter", 2.25), (None, .25), ("Page Down", 1)],
        [("Left Shift", 2.25), *[(c, 1) for c in "ZXCVBNM,./"], ("Right Shift", 2), ("Up", 1)],
        [("Left Ctrl", 1.25), ("Win", 1.25), ("Left Alt", 1.25), ("Space", 6.25),
         ("Right Alt", 1), ("Fn", 1), ("Right Ctrl", 1.25), ("Left", 1), ("Down", 1), ("Right", 1)],
    )
    labels = {"Backspace": "⌫", "Caps Lock": "Caps", "Page Up": "PgUp", "Page Down": "PgDn",
              "Left Shift": "Shift", "Right Shift": "Shift", "Left Ctrl": "Ctrl", "Right Ctrl": "Ctrl",
              "Left Alt": "Alt", "Right Alt": "Alt", "Up": "↑", "Down": "↓", "Left": "←", "Right": "→",
              "Space": ""}
    for y, row in enumerate(rows):
        x = 0.0
        for name, width in row:
            if name is not None:
                yield Key(name, labels.get(name, name), x, y, width)
            x += width


DUCKY = Device("ducky-one3-sf-ansi", "Ducky One 3 SF RGB", tuple(ansi_keys()), 5, 15, 0x01160001)
DEVICES = {DUCKY.id: DUCKY}
GROUPS = {
    "WASD": frozenset("WASD"),
    "Arrows": frozenset(("Up", "Down", "Left", "Right")),
    "Numbers": frozenset("1234567890"),
    "Modifiers": frozenset(("Left Ctrl", "Right Ctrl", "Win", "Left Alt", "Right Alt",
                             "Left Shift", "Right Shift", "Fn", "Caps Lock")),
    "Alphanumeric": frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"),
    "Navigation": frozenset(("Up", "Down", "Left", "Right", "Delete", "Page Up", "Page Down")),
}


@dataclass(frozen=True)
class Assignment:
    keys: tuple[str, ...]
    verified: bool


def validate_mapping(data, device=DUCKY):
    if (not isinstance(data, dict) or type(data.get("version")) is not int
            or data["version"] != 1 or data.get("device") != device.id):
        raise ValueError("Unsupported mapping format or device")
    slots = data.get("slots")
    if not isinstance(slots, dict) or len(slots) > device.slots:
        raise ValueError("Invalid slot assignments")
    result = {}
    for number, row in slots.items():
        if (not isinstance(number, str) or not number.isascii() or not number.isdecimal()
                or len(number) > 5 or str(int(number)) != number or not 0 <= int(number) < device.slots):
            raise ValueError("Invalid LED slot")
        if not isinstance(row, dict) or type(row.get("verified")) is not bool:
            raise ValueError("Missing verification status")
        keys = row.get("keys")
        if (not isinstance(keys, list) or len(keys) > len(device.keys)
                or any(not isinstance(key, str) or key not in device.key_ids for key in keys)
                or len(set(keys)) != len(keys)):
            raise ValueError("Invalid physical key assignment")
        result[int(number)] = Assignment(tuple(keys), row["verified"])
    return result


def mapping_json(mapping, device=DUCKY):
    return {"version": 1, "device": device.id, "slots": {
        str(slot): {"keys": list(row.keys), "verified": row.verified} for slot, row in sorted(mapping.items())
    }}
