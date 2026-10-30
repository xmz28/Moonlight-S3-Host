# Third-party notices

The packaged application includes the existing Python runtime, Pillow (JPEG codec,
image transforms, bundled default font), DXcam (MIT, DXGI screen capture), NumPy,
comtypes (COM bindings), MSS (compatible screen capture), pySerial (USB Wi-Fi setup), Tcl/Tk (GUI), and
the PyInstaller bootloader. Copies of available installed distribution licenses
are provided in `licenses/` by `tools/collect_licenses.py` during packaging.

PyInstaller has a bootloader exception allowing distribution of bundled applications;
see its included COPYING notice. Pillow includes notices for its bundled codecs.
The default Aileron font is labeled "No Rights Reserved" by its designer:
https://dotcolon.net/fonts/aileron/ . No installed dependency source has been modified.

The application adapter in capture.py targets DXcam 0.3.0. It selects monitors by
their exact desktop bounds and locally replaces the two capture-instance resource
release methods so owned comtypes pointers are released once by their destructors.
This avoids the explicit-release plus destructor-release issue observed during
capture teardown. These instance adapters are not changes to installed packages.
