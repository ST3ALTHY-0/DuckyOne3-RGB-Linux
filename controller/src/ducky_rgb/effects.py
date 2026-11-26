"""Effect declarations and deterministic vectorized RGB rendering."""
from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class Parameter:
    name: str
    kind: str
    default: object
    minimum: float = 0
    maximum: float = 1
    description: str = ""

    def validate(self, value):
        if self.kind == "color":
            return PALETTE.validate([value])[0]
        if self.kind == "palette":
            if (not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 16
                    or any(not isinstance(c, str) or len(c) != 7 or c[0] != "#"
                           or any(n not in "0123456789abcdefABCDEF" for n in c[1:]) for c in value)):
                raise ValueError("Use one to sixteen hex RGB colors")
            return list(value)
        if self.kind == "stops":
            if (not isinstance(value, (tuple, list)) or len(value) > 16
                    or any(type(stop) not in (int, float) or not 0 <= stop <= 1 for stop in value)
                    or any(left >= right for left, right in zip(value, value[1:]))):
                raise ValueError("Positions must increase strictly from 0 to 1")
            return list(value)
        if self.kind == "boolean":
            if type(value) is not bool:
                raise ValueError(f"Invalid {self.name}")
            return value
        if type(value) not in (int, float) or not self.minimum <= value <= self.maximum:
            raise ValueError(f"Invalid {self.name}")
        if self.kind == "integer" and type(value) is not int:
            raise ValueError(f"Invalid {self.name}")
        return value


PALETTE = Parameter("Palette", "palette", ("#635bff", "#3ee7bd", "#ea6398"),
                    description="Hex RGB stops separated by spaces")
COLOR = Parameter("Color", "color", "#635bff", description="RGB color")
FIRE_PALETTE = Parameter("Palette", "palette", ("#170306", "#fd4505", "#fff1a0"))
MATRIX_COLOR = Parameter("Color", "color", "#49ff83")
ANGLE = Parameter("Angle", "angle", 0.0, 0, 360, "Direction in degrees")
SCALE = Parameter("Scale", "number", 1.0, .1, 12, "Spatial cycles per key field")
SEED = Parameter("Seed", "integer", 5, 0, 65535, "Repeatable random pattern")
STOPS = Parameter("Stop positions", "stops", (), description="Normalized positions separated by spaces. Leave empty for evenly spaced stops.")
CENTER_X = Parameter("Center X", "number", .5)
CENTER_Y = Parameter("Center Y", "number", .5)
DECAY = Parameter("Fade seconds", "number", .9, .05, 10)


@dataclass(frozen=True)
class Effect:
    label: str
    category: str
    parameters: tuple[Parameter, ...]


def library():
    definitions = {
        "Static": {"solid": "Solid color", "paint": "Per-key paint", "linear": "Linear gradient",
                   "radial": "Radial gradient", "multicolor": "Multi-color gradient",
                   "checker": "Checkerboard", "zones": "Key zones", "alternate": "Alternating colors"},
        "Animated": {"rainbow": "Rainbow wave", "cycle": "Rainbow cycle", "breathing": "Breathing",
                     "color_cycle": "Color cycling", "moving": "Moving gradient", "horizontal": "Horizontal wave",
                     "vertical": "Vertical wave", "diagonal": "Diagonal wave", "radial_wave": "Radial wave",
                     "ripple": "Ripple", "rain": "Raindrops", "sparkles": "Sparkles", "stars": "Twinkling stars",
                     "fire": "Fire", "plasma": "Plasma", "aurora": "Aurora", "comet": "Comet",
                     "scanner": "Scanner", "chase": "Color chase", "matrix": "Matrix",
                     "random": "Random transitions", "pulse": "Color pulse", "rotating": "Rotating gradient"},
        "Reactive": {"keypress": "Keypress", "fade": "Keypress fade", "key_ripple": "Keypress ripple",
                     "heat": "Typing heatmap", "background": "Reactive background"},
    }
    for category, effects in definitions.items():
        for identifier, label in effects.items():
            single = {"solid", "breathing", "pulse", "scanner", "comet", "rain", "sparkles", "stars"}
            if identifier in {"paint", "rainbow", "cycle"}:
                parameters = ()
            elif identifier in single or category == "Reactive":
                parameters = (COLOR,)
            elif identifier == "fire":
                parameters = (FIRE_PALETTE,)
            elif identifier == "matrix":
                parameters = (MATRIX_COLOR,)
            else:
                parameters = (PALETTE,)
            if identifier in {"multicolor", "radial", "moving", "rotating"}:
                parameters += (STOPS,)
            if identifier in {"radial", "radial_wave", "ripple"}:
                parameters += (CENTER_X, CENTER_Y)
            if identifier in {"linear", "multicolor", "moving"}:
                parameters += (ANGLE,)
            if identifier in {"checker", "horizontal", "vertical", "diagonal", "radial_wave", "ripple", "chase", "plasma"}:
                parameters += (SCALE,)
            if identifier in {"rain", "sparkles", "stars", "fire", "matrix", "random"}:
                parameters += (SEED,)
            if category == "Reactive":
                parameters += (DECAY,)
            yield identifier, Effect(label, category, parameters)


EFFECTS = dict(library())


def rgb(color):
    return np.array(tuple(bytes.fromhex(color[1:])), dtype=np.float64) / 255


def ramp(colors, amount, stops=()):
    if stops and len(stops) == len(colors):
        return np.stack([np.interp(amount, stops, colors[:, channel]) for channel in range(3)], axis=1)
    value = np.clip(amount, 0, 1) * (len(colors) - 1)
    lo = value.astype(int)
    return colors[lo] + (colors[np.minimum(lo+1, len(colors)-1)] - colors[lo]) * (value-lo)[:, None]


def hue(phase):
    return np.clip(np.abs(((phase[:, None] * 6 + np.array([0, 4, 2])) % 6)-3)-1, 0, 1)


def render_effect(identifier, p, xy, t, reactions):
    n = len(xy)
    x, y = xy.T
    radius = np.hypot(x-p.get("Center X", .5), y-p.get("Center Y", .5)) * math.sqrt(2)
    angle = math.radians(p.get("Angle", 0))
    direction = (x-.5)*math.cos(angle)+(y-.5)*math.sin(angle)+.5
    wave = lambda value: .5+.5*np.sin(2*np.pi*value)
    scale = p.get("Scale", 1)
    colors = np.array([rgb(c) for c in p.get("Palette", (p.get("Color", COLOR.default),))])
    first = np.tile(colors[0], (n, 1))
    if identifier == "solid":
        return first
    if identifier == "rainbow":
        return hue(x-t)
    if identifier == "cycle":
        return hue(np.full(n, t))
    if identifier in ("linear", "multicolor", "radial", "moving", "rotating"):
        if identifier == "linear":
            colors = colors[[0, -1]]
        coordinates = {"linear": direction, "multicolor": direction, "radial": radius,
                       "moving": (direction-t) % 1,
                       "rotating": (x-.5)*np.cos(t*6.283)+(y-.5)*np.sin(t*6.283)+.5}
        return ramp(colors, coordinates[identifier], p.get("Stop positions", ()))
    if identifier in ("checker", "alternate", "zones"):
        index = {"checker": np.floor(x*15*scale)+np.floor(y*4*scale), "alternate": np.arange(n),
                 "zones": np.minimum((x*len(colors)).astype(int), len(colors)-1)}[identifier]
        return colors[index.astype(int) % len(colors)]
    if identifier in ("breathing", "pulse", "scanner", "comet"):
        level = {"breathing": np.full(n, wave(t)**2), "pulse": np.full(n, wave(t)**8),
                 "scanner": np.exp(-30*np.abs(x-wave(t))),
                 "comet": np.exp(-8*((t-x) % 1))}[identifier]
        return first*level[:, None]
    if identifier in ("color_cycle", "chase", "horizontal", "vertical", "diagonal", "radial_wave", "ripple",
                      "plasma", "aurora"):
        value = {"color_cycle": np.full(n, wave(t)), "chase": ((x*scale-t)*3) % 1,
                 "horizontal": wave(x*scale-t), "vertical": wave(y*scale-t),
                 "diagonal": wave((x+y)*scale-t), "radial_wave": wave(radius*scale-t),
                 "ripple": np.exp(-22*np.abs(radius*scale-t % 1)),
                 "plasma": (wave(x*scale+t)+wave(y*scale-t)+wave(radius*scale+t))/3,
                 "aurora": wave(x*.7+y*.4+t*.3+wave(x+t*.2)*.3)}[identifier]
        return ramp(colors, value)
    if EFFECTS[identifier].category == "Reactive":
        values = np.zeros(n)
        for origin, age, pressed, count in reactions:
            distance = np.linalg.norm(xy-origin, axis=1)
            if identifier == "key_ripple":
                strength = np.exp(-75*np.abs(distance-age/max(p["Fade seconds"], .05))) * max(0, 1-age/p["Fade seconds"])
            elif identifier == "background":
                strength = (1-distance/1.5)*max(0, 1-age/p["Fade seconds"])
            else:
                strength = (distance < .025) * (min(1, count/10) if identifier == "heat" else
                           int(pressed) if identifier == "keypress" else max(0, 1-age/p["Fade seconds"]))
            values = np.maximum(values, strength)
        return first*values[:, None]
    epoch = max(0, int(t*5))
    rng = np.random.default_rng([p.get("Seed", 5), epoch])
    noise = rng.random(n)
    if identifier == "random":
        next_noise = np.random.default_rng([p["Seed"], epoch+1]).random(n)
        return ramp(colors, noise*(1-t*5 % 1)+next_noise*(t*5 % 1))
    if identifier == "fire":
        return ramp(colors, (1-y)*.62+noise*.38)
    if identifier == "matrix":
        seed = p["Seed"]/65535
        return first * ((1-((y+t*1.8+x*(13+seed*11)+seed) % 1))**6)[:, None]
    if identifier == "rain":
        seed = p["Seed"]/65535
        return first * np.maximum(0, 1-5*((y-t*2+x*(7+seed*9)+seed) % 1))[:, None]
    if identifier == "stars":
        base = np.random.default_rng(p["Seed"]).random(n)
        return first * ((base>.69)*wave(base+t)**3)[:, None]
    return first*(noise>.91)[:, None]
