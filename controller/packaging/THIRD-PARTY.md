# Third-party components

The Studio source is GPL-3.0-only. Bundles assembled from Python wheels include independently licensed components. Review the license files accompanying each exact distribution before publishing a release and preserve all copyright notices.

| Component | Upstream license information |
|---|---|
| Python | [Python Software Foundation license](https://docs.python.org/3/license.html) |
| PySide6, Shiboken and Qt | [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html). Review Qt modules and applicable LGPL/GPL terms. |
| NumPy | [BSD-3-Clause and bundled libraries](https://numpy.org/doc/stable/license.html) |
| platformdirs | [MIT](https://github.com/platformdirs/platformdirs) |
| Cython hidapi and native HIDAPI | [Cython binding](https://github.com/trezor/cython-hidapi) and [HIDAPI](https://github.com/libusb/hidapi) |
| PyInstaller bootloader | [GPL with bootloader exception](https://pyinstaller.org/en/stable/license.html) |

Use the onedir layout so shared libraries remain replaceable. For a public release, archive the resolved dependency versions, the precise bundled license notices, and corresponding source or source offers where required. Packaging does not include proprietary firmware.
