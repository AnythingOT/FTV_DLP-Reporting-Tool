"""Log health check: finds what happened to DataLogPro logging in the fetched period.

Rules come from tests on FT View SE v16 (see README, "Log health rules"):
  normal stop      -> M=E (last value repeated, status C) ... gap ... M=B (status N, placeholder value)
  abnormal stop    -> gap without M=E (crash, kill, power loss); restart writes M=B
  PLC failure      -> status E, then U (placeholder values)
  start-up         -> status S for HMI tags right after M=B
  PLC Program mode -> NOT visible (frozen values, status C) - only a heartbeat tag reveals it
Always evaluated on ALL records, whatever "Good data only" is set to."""

from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass, field
from statistics import median

from .constants import (CRITICAL, GOOD, INFO, INTERVAL_DEVIATION, INTERVAL_RUN_MIN, MAX_GAP_EVENTS,
                        SEVERITY_RANK, START_STATUS, STATUS_SHORT, WARNING)
from .timeutil import NS, fmt_duration


@dataclass
class Event:
    start: int
    end: int
    severity: str
    kind: str
    text: str
    tags: list = field(default_factory=list)
    where: str = ""          # group of the tag

    @property
    def tag(self):
        return self.tags[0]


@dataclass
class TagSummary:
    tag: str
    group: str
    expected_s: float
    values: int
    good: int
    expected: int
    statuses: dict

    @property
    def completeness(self):
        return None if not self.expected else min(100.0, 100.0 * self.good / self.expected)


@dataclass
class HealthReport:
    overall: str
    events: list
    summaries: list
    excluded: int
    notes: list

    def counts(self):
        return Counter(e.severity for e in self.events)

    def headline(self):
        c = self.counts()
        if not c.get(CRITICAL) and not c.get(WARNING):
            return "Log health: OK" + (f" ({c[INFO]} info event(s))" if c.get(INFO) else "")
        parts = [f"{c[s]} {s.lower()}" for s in (CRITICAL, WARNING, INFO) if c.get(s)]
        return "Log health: " + ", ".join(parts)


def _steady(pairs):
    """Do these intervals form one regular rhythm?  -> (ok, median, regular pairs, other pairs)
    Regular = within 20 % of the median; ok if that covers at least 80 % (the first sample after a
    change is usually off-schedule) and at least INTERVAL_RUN_MIN intervals."""
    med = median(b - a for a, b in pairs)
    regular = [(a, b) for a, b in pairs if abs((b - a) - med) <= INTERVAL_DEVIATION * med]
    others = [(a, b) for a, b in pairs if abs((b - a) - med) > INTERVAL_DEVIATION * med]
    ok = len(regular) >= INTERVAL_RUN_MIN and len(regular) >= 0.8 * len(pairs)
    return ok, med, regular, others


def _tag_events(tag, h, exp_s, start_ns, end_ns, tol, is_heartbeat, periodic=True):
    ev = []
    vals = h["vals"]
    times = [t for t, _ in vals]
    ends = [t for t, m in h["markers"] if m == "E"]
    begins = [t for t, m in h["markers"] if m == "B"]

    def add(a, b, sev, kind, text):
        ev.append(Event(a, b, sev, kind, text, [tag]))

    # --- markers: normal stop / restart / abnormal restart / snapshot
    for e in ends:
        i = bisect_right(begins, e)
        if i < len(begins):
            add(e, begins[i], INFO, "stop", f"Logging stopped normally, restarted after {fmt_duration(begins[i] - e)}")
        else:
            add(e, e, INFO, "stop", "Logging stopped normally (no restart in this period)")
    for b in begins:
        j = bisect_left(times, b)
        prev = times[j - 1] if j > 0 else None
        if prev is None:
            add(b, b, INFO, "start", "Logging started")
        elif not any(prev <= e <= b for e in ends):
            add(prev, b, CRITICAL, "abnormal",
                f"Logging interrupted WITHOUT stop marker for {fmt_duration(b - prev)} (crash, kill or power loss)")
    for t, m in h["markers"]:
        if m == "S":
            add(t, t, INFO, "snapshot", "Snapshot (DataLogSnapshot)")
        elif m not in ("B", "E"):
            add(t, t, WARNING, "marker", f"Unknown marker '{m}'")

    # --- gaps and interval changes (need an expected interval)
    if exp_s:
        exp = exp_s * NS
        limit = tol * exp
        run = []      # consecutive intervals that are off the expected one

        def interval_event(regular, med):
            add(regular[0][0], regular[-1][1], WARNING, "interval",
                f"Logging interval about {med / NS:.2f} s instead of configured {exp_s:g} s")

        def flush():
            if not run:
                return
            gaps = [(a, b) for a, b in run if b - a > limit]
            small = [(a, b) for a, b in run if b - a <= limit]
            if periodic and len(gaps) >= INTERVAL_RUN_MIN:
                ok, med, regular, others = _steady(gaps)
                if ok:      # regular but slower than configured: one interval event, not hundreds of gaps
                    interval_event(regular, med)
                    gaps = [(a, b) for a, b in others if b - a > med]      # only real outages remain
            if len(gaps) > MAX_GAP_EVENTS:
                longest = max(b - a for a, b in gaps)
                add(gaps[0][0], gaps[-1][1], CRITICAL, "gap",
                    f"{len(gaps)} gaps without stop marker (longest {fmt_duration(longest)})")
            else:
                for a, b in gaps:
                    add(a, b, CRITICAL, "gap", f"No data for {fmt_duration(b - a)} (no stop marker)")
            if periodic and len(small) >= INTERVAL_RUN_MIN:
                ok, med, regular, _ = _steady(small)
                if ok:
                    interval_event(regular, med)
            run.clear()

        for a, b in zip(times, times[1:]):
            d = b - a
            off = d > limit or (periodic and abs(d - exp) > INTERVAL_DEVIATION * exp)
            if off and not (any(a <= e <= b for e in ends) or any(a < x <= b for x in begins)):
                run.append((a, b))
            else:
                flush()     # a normal interval, or one explained by stop/start markers
        flush()
        # At the edges of the period, judge by the rhythm the log actually has there: a log that
        # runs slower than configured (already reported above) has not "stopped" after one interval.
        def edge_limit(part):
            ds = [b - a for a, b in zip(part, part[1:])]
            return max(limit, tol * median(ds)) if ds else limit

        if times and times[0] - start_ns > edge_limit(times[:11]) and not (begins and begins[0] <= times[0]):
            add(start_ns, times[0], WARNING, "late", f"No data for the first {fmt_duration(times[0] - start_ns)} of the period")
        if times and end_ns - times[-1] > edge_limit(times[-11:]) and not (ends and ends[-1] >= times[-1]):
            add(times[-1], end_ns, CRITICAL, "stopped",
                f"No data since this time ({fmt_duration(end_ns - times[-1])}), no stop marker")
    if not vals and not h["markers"]:
        add(start_ns, end_ns, WARNING, "nodata", "No data in this period")

    # --- status runs
    i = 0
    while i < len(vals):
        t, s = vals[i]
        if s == GOOD:
            i += 1
            continue
        if s == START_STATUS and t in begins:
            i += 1
            j = i
            while j < len(vals) and vals[j][1] == "S":
                j += 1
            if j > i:
                add(vals[i][0], vals[j - 1][0], INFO, "startup_stale", f"Stale values after start ({j - i} sample(s))")
            i = j
            continue
        j = i
        while j < len(vals) and vals[j][1] != GOOD and not (vals[j][1] == START_STATUS and vals[j][0] in begins):
            j += 1
        run = Counter(s for _, s in vals[i:j])
        unknown = [k for k in run if k not in STATUS_SHORT]
        text = "Bad data: " + ", ".join(f"{STATUS_SHORT.get(k, 'unknown')} ({k}) x{n}" for k, n in sorted(run.items()))
        add(vals[i][0], vals[j - 1][0], CRITICAL if unknown else WARNING, "badstatus",
            text + (" - UNKNOWN status code" if unknown else ""))
        i = j

    # --- heartbeat frozen: same good value for longer than the gap tolerance (needs a real counter tag)
    if is_heartbeat:
        hb = [(t, v) for t, v, s in h["hb"] if s == GOOD]
        min_frozen = tol * exp_s * NS if exp_s else None
        step_limit = tol * exp_s * NS if exp_s else None
        k = 0
        while k < len(hb) - 1:
            j = k
            while (j + 1 < len(hb) and hb[j + 1][1] == hb[k][1]
                   and (step_limit is None or hb[j + 1][0] - hb[j][0] <= step_limit)  # never across a gap
                   and not any(hb[j][0] <= e < hb[j + 1][0] for e in ends)):
                j += 1
            span = hb[j][0] - hb[k][0]
            frozen = span > min_frozen if min_frozen else (j - k) >= 2
            if j > k and frozen:
                add(hb[k][0], hb[j][0], CRITICAL, "heartbeat",
                    f"Heartbeat frozen at {hb[k][1]} for {fmt_duration(span)} (PLC not running or data frozen)")
            k = j + 1
    return ev


def analyze(health_input, tags, groups, intervals, start_ns, end_ns, now_ns, tolerance,
            heartbeat_tag="", excluded=0, periodic=None):
    """health_input: tag -> {"vals", "markers", "hb"}; tags: displayed tags; groups: tag -> group;
    intervals: tag -> expected seconds or None; periodic: tags logged at a fixed interval (only for
    those is the interval itself checked; On change tags may legitimately log faster).
    now_ns should be the HMI PC's clock, so a clock difference to this PC causes no false alarm."""
    if periodic is None:
        periodic = {t for t, v in intervals.items() if v}
    end_eff = min(end_ns, now_ns)
    check = list(tags) + ([heartbeat_tag] if heartbeat_tag and heartbeat_tag not in tags else [])
    raw, summaries, notes = [], [], []
    for tag in check:
        h = health_input.get(tag, {"vals": [], "markers": [], "hb": []})
        exp_s = intervals.get(tag)
        raw += _tag_events(tag, h, exp_s, start_ns, end_eff, tolerance, tag == heartbeat_tag, tag in periodic)
        statuses = Counter(s for _, s in h["vals"])
        expected = int((end_eff - start_ns) / (exp_s * NS)) if exp_s and tag in periodic and end_eff > start_ns else 0
        summaries.append(TagSummary(tag, groups.get(tag, ""), exp_s, len(h["vals"]), statuses.get(GOOD, 0),
                                    expected, dict(statuses)))
    no_interval = [t for t in tags if not intervals.get(t)]
    if no_interval:
        notes.append(f"Gap check not possible for {len(no_interval)} tag(s) without an expected interval "
                     "(On change without heartbeat, On demand, or not in the imported configuration).")
    if heartbeat_tag and not health_input.get(heartbeat_tag, {}).get("vals"):
        notes.append(f"Heartbeat tag '{heartbeat_tag}' has no data in this period.")
    elif heartbeat_tag and heartbeat_tag not in periodic:
        notes.append(f"Heartbeat tag '{heartbeat_tag}' should be logged periodically (and be in the imported "
                     "configuration), otherwise a frozen value cannot be detected reliably.")

    # tag-wise, like FactoryTalk Diagnostics: one event per tag, in column order, then by time
    order = {t: i for i, t in enumerate(check)}
    events = sorted(raw, key=lambda e: (order.get(e.tags[0], 0), e.start, SEVERITY_RANK[e.severity]))
    for e in events:
        e.where = groups.get(e.tags[0], "")
    worst = min((SEVERITY_RANK[e.severity] for e in events), default=None)
    overall = "OK" if worst is None or worst == SEVERITY_RANK[INFO] else (CRITICAL if worst == 0 else WARNING)
    return HealthReport(overall, events, summaries, excluded, notes)
