# Third-party notices

FTV_DLP-Reporting-Tool is licensed under the GNU GPL v3.0 only (see `LICENSE`). It uses the
following work by others. Every licence below is compatible with the GPL-3.0 and allows use,
change and redistribution with the notice kept.

## Python packages

Installed from `requirements.txt`; none of them is copied into this repository.

| Package | Used for | Licence |
|---|---|---|
| influxdb-client | reading DataLogPro data from InfluxDB | MIT |
| &nbsp;&nbsp;reactivex, urllib3, setuptools | used by influxdb-client | MIT |
| &nbsp;&nbsp;python-dateutil | used by influxdb-client | Apache-2.0 / BSD-3-Clause (dual) |
| &nbsp;&nbsp;six | used by python-dateutil | MIT |
| &nbsp;&nbsp;typing_extensions | used by reactivex | PSF-2.0 |
| &nbsp;&nbsp;certifi | CA certificates for HTTPS, used by influxdb-client | **MPL-2.0** |
| openpyxl, et-xmlfile | Excel export | MIT |
| reportlab | PDF export | BSD |
| &nbsp;&nbsp;pillow, charset-normalizer | used by reportlab | MIT-CMU, MIT |

The indented rows are dependencies of dependencies; the exact set depends on the versions pip
picks, so the release build lists what it actually bundled (see below).

## Runtime bundled in `DLPReport.exe`

| Component | Licence | Source |
|---|---|---|
| Python, incl. tkinter | PSF License | https://www.python.org/ |
| Tcl/Tk (behind tkinter) | Tcl/Tk licence (BSD-style) | https://www.tcl-lang.org/ |
| PyInstaller bootloader | GPL-2.0-or-later with the bootloader exception | https://pyinstaller.org/ |

## The .exe

`DLPReport.exe` contains copies of all of the above, so passing it on means passing their
licences on too. The release workflow and `build.bat` write the full texts to
`THIRD_PARTY_LICENSES.txt` (made by `tools/collect_licenses.py` from the packages that were
actually bundled), and the release attaches it next to the exe. **Give it along with the exe.**

certifi is MPL-2.0: anyone who gets it in binary form must be able to get its source. It is
bundled unchanged; its source is at https://github.com/certifi/python-certifi and on PyPI, and
`THIRD_PARTY_LICENSES.txt` says so.

## Trademarks

Rockwell Automation, FactoryTalk and FactoryTalk View are trademarks of Rockwell Automation,
Inc. InfluxDB is a trademark of InfluxData Inc. They are used here only to
say which software this tool works with. FTV_DLP-Reporting-Tool is not affiliated with or
endorsed by either company.
