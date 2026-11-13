"""Time zones and exact (nanosecond) timestamps.

InfluxDB stores nanoseconds; Python datetime holds only microseconds. Timestamps are therefore
kept as integer nanoseconds since the epoch and formatted without losing digits."""

import calendar
from datetime import datetime, timedelta, timezone
from functools import lru_cache

NS = 1_000_000_000


def tz_choices():
    items = [("Same as this PC", "local")]
    for m in sorted(set(range(-12 * 60, 14 * 60 + 1, 30)) | {345, 525, 765}):
        sign = "+" if m >= 0 else "-"
        items.append((f"UTC{sign}{abs(m) // 60:02d}:{abs(m) % 60:02d}", m))
    return items


def profile_tz(profile):
    tz = (profile or {}).get("tz", "local")
    return None if tz == "local" else timezone(timedelta(minutes=int(tz)))


def now_in(tz):
    return datetime.now(tz) if tz else datetime.now().astimezone()


def naive_to_aware(naive, tz):
    return naive.replace(tzinfo=tz) if tz else naive.astimezone()


def flux_time(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dt_to_ns(dt):
    return calendar.timegm(dt.astimezone(timezone.utc).timetuple()) * NS + dt.microsecond * 1000


def parse_rfc3339_ns(text):
    """'2026-11-10T02:41:40.8564209Z' -> exact integer nanoseconds (UTC)."""
    text = text.strip()
    if text.endswith("Z"):
        text = text[:-1]
    base, _, frac = text.partition(".")
    return _epoch_seconds(base) * NS + int((frac + "000000000")[:9])


@lru_cache(maxsize=200_000)
def _epoch_seconds(base):
    """'YYYY-MM-DDTHH:MM:SS' (UTC) -> epoch seconds. Cached: all tags of a group share timestamps."""
    return calendar.timegm((int(base[0:4]), int(base[5:7]), int(base[8:10]),
                            int(base[11:13]), int(base[14:16]), int(base[17:19])))


def fmt_ns(ns, tz):
    """Exact local time: 'YYYY-MM-DD HH:MM:SS.nnnnnnnnn' (9 digits, nothing dropped)."""
    seconds, frac = divmod(ns, NS)
    dt = datetime.fromtimestamp(seconds, timezone.utc)
    dt = dt.astimezone(tz) if tz else dt.astimezone()
    return f"{dt:%Y-%m-%d %H:%M:%S}.{frac:09d}"


def fmt_duration(ns):
    s = ns / NS
    if s < 60:
        return f"{s:.1f} s"
    m, s = divmod(int(round(s)), 60)
    if m < 60:
        return f"{m} min {s} s"
    h, m = divmod(m, 60)
    return f"{h} h {m} min"
