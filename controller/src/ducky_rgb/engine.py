"""Render host layers in normalized sRGB channel space and emit RGB8."""
from dataclasses import dataclass, field

import numpy as np

from .devices import DUCKY
from .effects import EFFECTS, render_effect, rgb

BLENDS = ("Normal", "Additive", "Multiply", "Screen", "Overlay", "Maximum", "Minimum", "Difference")


@dataclass
class Layer:
    effect: str = "solid"
    name: str = "Solid color"
    enabled: bool = True
    opacity: float = 1.0
    brightness: float = 1.0
    speed: float = 1.0
    phase: float = 0.0
    blend: str = "Normal"
    mask: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)
    paint: dict[str, str] = field(default_factory=dict)

    def settings(self):
        return {parameter.name: self.params.get(parameter.name, parameter.default)
                for parameter in EFFECTS[self.effect].parameters}


def composite(base, top, mode, alpha):
    if mode == "Normal":
        result = top
    elif mode == "Additive":
        result = np.minimum(1, base+top)
    elif mode == "Multiply":
        result = base*top
    elif mode == "Screen":
        result = 1-(1-base)*(1-top)
    elif mode == "Overlay":
        result = np.where(base < .5, 2*base*top, 1-2*(1-base)*(1-top))
    elif mode == "Maximum":
        result = np.maximum(base, top)
    elif mode == "Minimum":
        result = np.minimum(base, top)
    elif mode == "Difference":
        result = abs(base-top)
    else:
        raise ValueError("Unknown blend mode")
    return base+(result-base)*alpha


class Renderer:
    def __init__(self, device=DUCKY, mapping=None):
        self.device = device
        self.mapping = mapping or {}
        width = max(key.x+key.width for key in device.keys)
        height = max(key.y for key in device.keys)+1
        self.keys = {k.id: ((k.x+k.width/2)/width, (k.y+.5)/height) for k in device.keys}
        self.ids = list(self.keys)
        self.preview = np.array(list(self.keys.values()))
        self.slot_keys = [self.mapping[i].keys if i in self.mapping and self.mapping[i].verified else ()
                          for i in range(device.slots)]
        self.key_slots = {key: [i for i, keys in enumerate(self.slot_keys) if key in keys]
                          for key in self.ids}
        self.used = np.array([i not in self.mapping or not self.mapping[i].verified or bool(self.mapping[i].keys)
                              for i in range(device.slots)])
        self.xy = np.array([np.mean([self.keys[k] for k in keys], axis=0) if keys else
                            ((i%device.slots_per_bank+.5)/device.slots_per_bank,
                             (i//device.slots_per_bank+.5)/device.banks)
                            for i, keys in enumerate(self.slot_keys)])

    def _render(self, xy, keys, layers, stamp, reactions, gamma):
        canvas = np.zeros((len(xy), 3))
        for layer in layers:
            if not layer.enabled or not layer.opacity:
                continue
            if layer.effect == "paint":
                colors = np.zeros_like(canvas)
                active = np.zeros(len(xy), dtype=bool)
                for i, group in enumerate(keys):
                    match = next((key for key in group if key in layer.paint), None)
                    if match is not None:
                        colors[i] = rgb(layer.paint[match])
                        active[i] = True
            else:
                colors = render_effect(layer.effect, layer.settings(), xy, stamp*layer.speed+layer.phase, reactions)
                active = np.ones(len(xy), dtype=bool)
            if layer.mask:
                permitted = set(layer.mask)
                active &= [not permitted.isdisjoint(group) for group in keys]
            canvas = composite(canvas, colors*layer.brightness, layer.blend, (active*layer.opacity)[:, None])
        return np.rint(np.clip(canvas, 0, 1)**gamma*255).astype(np.uint8)

    def render(self, layers, stamp, events=(), *, gamma=1.0, preview_brightness=1.0):
        reactions = [(self.keys[key], age, pressed, count) for key, age, pressed, count in events
                     if key in self.keys and age >= 0]
        physical = self._render(self.preview, [(k,) for k in self.ids], layers, stamp, reactions, gamma)
        slots = self._render(self.xy, self.slot_keys, layers, stamp, reactions, gamma)
        slots[~self.used] = 0
        for index, key in enumerate(self.ids):
            if group := self.key_slots[key]:
                physical[index] = np.rint(np.mean(slots[group], axis=0))
        return dict(zip(self.ids, np.rint(physical*preview_brightness).astype(np.uint8).tolist())), slots.tobytes()
