"""DataLogPro schema names, limits and UI constants."""

# --- DataLogPro schema in InfluxDB (Rockwell "InfluxDB storage format and schemas", FT View 16)
MEASUREMENT = "TagData"
VALUE_FIELDS = ("V_I", "V_D", "V_B", "V_S")
MARKER_FIELD = "M"
GOOD = "C"
START_STATUS = "N"
STATUS_TEXT = {
    "C": "Common (good)",
    "N": "Start record - value is a placeholder (observed, not documented by Rockwell)",
    "E": "Error",
    "S": "Stale",
    "U": "Uninitialized",
    "D": "Tag disabled",
}
STATUS_SHORT = {"C": "Good", "N": "Start record", "E": "Error", "S": "Stale", "U": "Uninitialized", "D": "Disabled"}
MARKER_TEXT = {"B": "Begin", "E": "End", "S": "Snapshot"}
TYPE_LABEL = {"V_B": "BOOL", "V_I": "INT", "V_D": "REAL", "V_S": "STRING"}
TAG_LOOKBACK = "-30d"          # tag list = tags logged in the last 30 days

# --- limits
EXCEL_MAX_ROWS = 1_048_576
PREVIEW_ROWS = 1000
PDF_TAGS_PER_SECTION = 8
PDF_ROWS_PER_TABLE = 400
PDF_ROWS_PER_PAGE = 32
PDF_PAGE_WARN = 200
INTERVAL_DEVIATION = 0.2       # 20 % off the configured interval = interval change
INTERVAL_RUN_MIN = 5           # ... sustained for at least 5 samples
MAX_GAP_EVENTS = 20            # more gaps than this in one stretch are reported as one event

# --- grouping
UNGROUPED = "(Ungrouped)"
NOT_IN_EXPORT = "(Not in imported configuration)"

# --- health severities
CRITICAL, WARNING, INFO = "Critical", "Warning", "Info"
SEVERITY_RANK = {CRITICAL: 0, WARNING: 1, INFO: 2}

# --- UI
QUICK_RANGES = [("Last 30 minutes", 30), ("Last 1 hour", 60), ("Last 2 hours", 120),
                ("Last 4 hours", 240), ("Last 8 hours", 480), ("Last 12 hours", 720),
                ("Last 24 hours", 1440)]
ACCENT = "#005FB8"
TREE_INDENT = 36
GROUP_ROW_BG = "#E8EFF7"
SEVERITY_COLOR = {CRITICAL: "#B42318", WARNING: "#B54708", INFO: "#475467", "OK": "#1A7F37"}
EXCEL_SHEET = "Sheet1"
