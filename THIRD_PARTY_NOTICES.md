# Third-party notices

The packaged application includes the existing Python runtime, Pillow (JPEG codec,
image transforms, bundled default font), MSS (screen capture), Tcl/Tk (GUI), and
the PyInstaller bootloader. Copies of available installed distribution licenses
are provided in `licenses/` by `tools/collect_licenses.py` during packaging.

PyInstaller has a bootloader exception allowing distribution of bundled applications;
see its included COPYING notice. Pillow includes notices for its bundled codecs.
The default Aileron font is labeled "No Rights Reserved" by its designer:
https://dotcolon.net/fonts/aileron/ . No dependency source has been modified.
