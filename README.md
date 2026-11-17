# DataLogPro Report Tool 1.0.1

Exports **FactoryTalk View SE v16 DataLogPro** data from the built-in InfluxDB of an HMI PC (local or
over the network) to **Excel, CSV and PDF**, with a tag-wise **log health check**.

**Data is exported exactly as stored in InfluxDB** – values as stored (booleans `true`/`false`, all
digits of REALs), timestamps with nanoseconds. No averaging, interpolation or rounding.
(Excel itself keeps at most 15 significant digits of a number; CSV and PDF are exact text.)

## 1. Set up each HMI PC (once)

1. **Users** – run `create_influx_users.bat` on the HMI PC (as the Windows user that has the influx CLI
   configured). It creates an admin (owner) and a read-only member account and never touches `FTViewSE`.
2. **Remote access** (tool on another PC): on the HMI PC `netstat -ano | findstr :8086` must show
   `0.0.0.0:8086`; allow inbound TCP 8086 in Windows Firewall (on non-domain PCs for the **Public**
   profile). Use the HMI PC's **IP address**. Test: `Test-NetConnection <IP> -Port 8086`.
3. **Heartbeat tag (optional)** – a PLC counter incrementing every second, logged **periodically** in
   DataLogPro. It is the only way to detect a PLC in Program mode (see section 4).

### Security notes

- The built-in InfluxDB of FactoryTalk View listens on plain **HTTP**. The token or password and all
  data cross the network unencrypted, so use the tool only on the plant network (or through a VPN),
  never across an untrusted network.
- Always sign in with the **read-only member** account, not the admin account.
- If you put InfluxDB behind HTTPS, tick **Use HTTPS** in the HMI PC's advanced settings. Certificate
  checking is on by default for new HMI PCs; switch it off only for a self-signed certificate you trust.

## 2. Install and run

Python 3.12 or 3.13 recommended.

```
py -m pip install -r requirements.txt
py main.py
```

Build a single exe (runs the unit tests first): `build.bat` → `dist\DLPReport.exe`

## 3. Use

1. **⚙ Settings → HMI PCs → Add**: machine name, IP, member username/password or read-only token,
   machine time zone, optional heartbeat tag → **Test connection**. Under **Log groups** import the
   DataLogPro export (DataLogPro editor → *Export*); re-import when the log groups change. **Save**.
2. Pick the **HMI PC** (connects automatically). The tag list shows every tag logged in the last 30 days,
   per log group (click ▸/▾ to expand, click a group to tick all its tags).
3. Choose the **period** and **Good data only** (status C), then **Fetch data**. Large fetches ask first.
4. **Preview** shows the data, **Log health** shows per tag what happened to logging
   (times there are shortened to 4 decimals; exports keep all digits).
5. **Download Excel / CSV / PDF** – saved to the output folder; **Open file / Open folder**.

| Format | Content |
|---|---|
| Excel | `Sheet1`: group band + tag names; each log group is a collapsible column group (+/− on the narrow separator column left of the group); status columns (Good data only off) are hidden at outline level 2 – shown automatically for tags with E/S/U/D values, button **3** shows all. **Info** and **Events** sheets |
| CSV | One header row, exact text, all status columns – for further processing. Companion `*_events.csv`. If you open the CSV in Excel, Excel itself reformats some values (`true` → `TRUE`, long numbers) |
| PDF | Page 1: information, log health events per tag, per-tag summary, status codes. Then the data |

## 4. Log health rules (from tests on FT View SE v16)

| What happened | What DataLogPro writes | Reported as |
|---|---|---|
| Logging stopped normally | `M=E` (last value repeated) … gap … `M=B` (status **N**, placeholder value 0/false) | Info |
| Crash / kill / power loss of the logging component | gap **without** `M=E` | **Critical** |
| HMI server start-up | status **S** (stale) for HMI tags right after `M=B` | Info |
| PLC fault / not reachable | status **E**, then **U** with placeholder values | **Warning** |
| PLC in Program mode | nothing visible (last values, status C) | only via heartbeat tag: **Critical** |
| Interval changed in DataLogPro | interval differs from the imported configuration | **Warning** |
| HMI **client** stopped / killed | nothing – logging continues | – |

**Gap tolerance** (Settings → General → Advanced, default 2.5): a gap is reported when no value arrives
within *expected interval × gap tolerance* (10 s × 2.5 = 25 s). A single skipped sample is ignored.
The expected interval comes from the imported configuration (Periodic, or On change with heartbeat);
a tag in several log groups is judged by the fastest of them. The check always uses **all** values,
whatever *Good data only* is set to. Further details:

- "No data since …" compares the last value with the **HMI PC's clock**, so a clock difference between
  the HMI PC and this PC causes no false alarm.
- A log that runs steadily slower or faster than configured is reported once as an interval change,
  not as hundreds of gaps. More than 20 irregular gaps in a row are summarised in one event.
- On change tags may log faster than their heartbeat rate; only missing heartbeats are reported.
- Not detectable: values overwritten after the HMI PC's clock was set back, and the *cause* of an
  interruption (see FactoryTalk Diagnostics on the HMI PC).

## 5. Project structure

```
main.py  build.bat  create_influx_users.bat  requirements.txt
dlpreport/
  app_info.py  constants.py  settings.py  timeutil.py
  influx.py        queries (InfluxDB CSV text, nanoseconds)
  dlp_export.py    DataLogPro export import
  table.py  health.py  exporter.py
  writers/         excel.py, csv_out.py, pdf.py
  ui/              main_window, tag_panel, period_panel, results_panel, settings_dialog, widgets, theme
tests/             unit tests with real DataLogPro data from the test VM
```

Licences: influxdb-client (MIT), openpyxl (MIT), reportlab (BSD), sv-ttk (MIT), PyInstaller
(GPL with bootloader exception – the built exe may be distributed freely).
