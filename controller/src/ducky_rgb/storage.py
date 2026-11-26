"""Versioned portable profiles and atomic local persistence."""
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import tempfile

from platformdirs import user_config_path, user_data_path

from .devices import DEVICES, DUCKY
from .effects import EFFECTS, PALETTE
from .engine import BLENDS, Layer

MAX_JSON = 512 * 1024
MAX_LIBRARY = 16 * 1024 * 1024


@dataclass
class Profile:
    name: str = "Spectrum"
    description: str = ""
    device: str = DUCKY.id
    brightness: float = .75
    gamma: float = 1
    fps: int = 30
    overlays: int = 0
    layers: list[Layer] = field(default_factory=lambda: [Layer("rainbow", "Rainbow wave", speed=.24)])
    groups: dict[str, list[str]] = field(default_factory=dict)

    def encode(self):
        return {"version": 2, **asdict(self)}


def read_json(path: Path, limit=MAX_JSON):
    with path.open("rb") as stream:
        content = stream.read(limit+1)
    if len(content) > limit:
        raise ValueError("JSON document is too large")
    return json.loads(content)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temp = Path(stream.name)
            json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp and temp.exists():
            temp.unlink()


def validate_profile(value):
    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] not in (1, 2):
        raise ValueError("Unsupported profile version")
    data = dict(value)
    if data["version"] == 1:
        data.setdefault("gamma", 1)
        data.setdefault("groups", {})
    device_id = data.get("device", DUCKY.id)
    if not isinstance(device_id, str) or device_id not in DEVICES:
        raise ValueError("Unknown profile device")
    device = DEVICES[device_id]

    def number(value, low, high, kind=None):
        if type(value) not in (int, float) or (kind and type(value) is not kind) or not low <= value <= high:
            raise ValueError("Profile numeric value out of range")
        return value

    def string(value, limit, allow_empty=False):
        if not isinstance(value, str) or len(value) > limit or (not allow_empty and not value.strip()):
            raise ValueError("Invalid profile text")
        return value

    def keys(value):
        if (not isinstance(value, list) or len(value) > len(device.keys)
                or any(not isinstance(k, str) or k not in device.key_ids for k in value)):
            raise ValueError("Invalid physical key mask")
        return list(dict.fromkeys(value))

    rows = data.get("layers")
    if not isinstance(rows, list) or len(rows) > 32:
        raise ValueError("Expected up to 32 effect layers")
    layers = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("effect"), str) or row["effect"] not in EFFECTS:
            raise ValueError("Unknown effect")
        effect = EFFECTS[row["effect"]]
        params, paint = row.get("params", {}), row.get("paint", {})
        if not isinstance(params, dict) or not isinstance(paint, dict):
            raise ValueError("Invalid effect parameters")
        keys(list(paint))
        enabled, blend = row.get("enabled", True), row.get("blend", "Normal")
        if type(enabled) is not bool or blend not in BLENDS:
            raise ValueError("Invalid layer blend or visibility")
        checked = {p.name: p.validate(params[p.name]) for p in effect.parameters if p.name in params}
        stops = checked.get("Stop positions")
        if stops and len(stops) != len(checked.get("Palette", PALETTE.default)):
            raise ValueError("Gradient stop count does not match its palette")
        layers.append(Layer(
            row["effect"], string(row.get("name", effect.label), 80), enabled,
            number(row.get("opacity", 1), 0, 1), number(row.get("brightness", 1), 0, 1),
            number(row.get("speed", 1), 0, 8), number(row.get("phase", 0), 0, 60), blend,
            keys(row.get("mask", [])),
            checked,
            {k: PALETTE.validate([v])[0] for k, v in paint.items()},
        ))
    groups = data.get("groups", {})
    if not isinstance(groups, dict) or len(groups) > 32:
        raise ValueError("Invalid key groups")
    return Profile(string(data.get("name"), 80), string(data.get("description", ""), 1500, True),
                   device_id, number(data.get("brightness", .75), 0, 1),
                   number(data.get("gamma", 1), .2, 4), number(data.get("fps", 30), 1, 60, int),
                   number(data.get("overlays", 0), 0, 15, int), layers,
                   {string(name, 40): keys(ids) for name, ids in groups.items()})


def examples():
    return [Profile(), Profile("Midnight", layers=[Layer("linear", "Violet to mint", params={
        "Palette": ["#30144d", "#7158ff", "#5ce6c6"]})]),
        Profile("Aurora", layers=[Layer("aurora", "Northern lights", speed=.4),
                                  Layer("stars", "Starlight", opacity=.4, blend="Screen")]),

        Profile("Desert Dusk", "A diagonal fade from ink violet to warm amber.", brightness=.70, layers=[
            Layer("multicolor", "Violet, rose and amber", params={
                "Palette": ["#21113d", "#753663", "#d65d64", "#ffbd72"],
                "Angle": 19, "Stop positions": [0, .32, .66, 1]})]),
        Profile("Glacier", "A blue ice field with a soft white center.", brightness=.66, layers=[
            Layer("radial", "Frosted glass", params={
                "Palette": ["#e0faff", "#5bcce7", "#2354a4", "#101b44"],
                "Center X": .37, "Center Y": .46, "Stop positions": [0, .28, .62, 1]})]),
        Profile("Sakura", "Rose, pink and peach from the top row to the bottom.", brightness=.62, layers=[
            Layer("multicolor", "Cherry blossom", params={
                "Palette": ["#63375e", "#bf6296", "#f6a7be", "#ffd0af"], "Angle": 90})]),
        Profile("Jade Circuit", "A quiet green grid with a traveling mint highlight.", brightness=.58, layers=[
            Layer("checker", "Board traces", params={"Palette": ["#0e493f", "#18695c"], "Scale": 1}),
            Layer("comet", "Mint trace", opacity=.66, speed=.26, blend="Screen",
                  params={"Color": "#74ffcb"})]),
        Profile("After Hours", "A deep indigo field with magenta and turquoise waves.", brightness=.73, layers=[
            Layer("plasma", "Neon currents", speed=.19, params={
                "Palette": ["#171543", "#4935a2", "#d73793", "#3cd2bb"], "Scale": 1.3})]),
        Profile("Ember Gold", "Warm coal and brass with a restrained amber pulse.", brightness=.67, layers=[
            Layer("radial", "Coal bed", params={
                "Palette": ["#fbb048", "#b44d24", "#551d19", "#21121a"], "Center X": .7, "Center Y": .6}),
            Layer("pulse", "Amber glow", opacity=.36, speed=.20, blend="Screen",
                  params={"Color": "#ff9552"})]),
        Profile("Deep Sea", "Navy, teal and seafoam moving in broad diagonal bands.", brightness=.64, layers=[
            Layer("diagonal", "Tidal bands", speed=.17, params={
                "Palette": ["#101f45", "#155a82", "#1ba89b", "#99e3c7"], "Scale": 1.0})]),
        Profile("Moonstone", "A low-brightness fade from warm pearl to blue-gray.", brightness=.42, layers=[
            Layer("linear", "Pearl to slate", params={"Palette": ["#e3d4bb", "#5379bd"], "Angle": 22})]),
    ]


class Storage:
    def __init__(self, config=None, data=None):
        self.config = config or user_config_path("Ducky RGB Studio", appauthor=False)
        self.data = data or user_data_path("Ducky RGB Studio", appauthor=False)
        self.library = self.data / "profiles.json"
        self.settings = self.config / "settings.json"
        self.mapping = self.data / "ansi-led-mapping.json"

    def load_profiles(self):
        if not self.library.exists():
            return examples()
        rows = read_json(self.library, MAX_LIBRARY)
        if not isinstance(rows, list) or not 1 <= len(rows) <= 128:
            raise ValueError("Invalid profile library")
        return [validate_profile(row) for row in rows]

    def save_profiles(self, profiles):
        write_json(self.library, [profile.encode() for profile in profiles])
