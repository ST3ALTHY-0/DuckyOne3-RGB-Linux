"""Device-independent RGB8 frame generators."""
import colorsys

BANKS = 5
SLOTS = 15


def solid(rgb):
    return bytes(rgb) * (BANKS * SLOTS)


def gradient(left, right):
    return bytes(round(a + (b - a) * index / (SLOTS - 1))
                 for _ in range(BANKS) for index in range(SLOTS)
                 for a, b in zip(left, right))


def rainbow(phase):
    return bytes(round(channel * 255)
                 for _ in range(BANKS) for index in range(SLOTS)
                 for channel in colorsys.hsv_to_rgb((phase + index / SLOTS) % 1, 1, 1))
