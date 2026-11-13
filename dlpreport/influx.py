"""InfluxDB access. Values are read as InfluxDB's own CSV text (RFC3339Nano timestamps), so
nothing is converted, rounded or truncated on the way in."""

import logging

from .constants import MARKER_FIELD, MEASUREMENT, TAG_LOOKBACK, VALUE_FIELDS
from .settings import log_path
from .timeutil import dt_to_ns, flux_time, parse_rfc3339_ns

log = logging.getLogger("dlpreport")


def flux_str(s):
    """Quote as a Flux string literal (escapes \\, " and ${)."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("${", "\\${") + '"'


def tag_filter(tags):
    return "contains(value: r.TagName, set: [" + ", ".join(flux_str(t) for t in tags) + "])"


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def profile_url(p):
    return f"{'https' if p.get('https') else 'http'}://{p.get('host', '').strip()}:{int(p.get('port', 8086))}"


def parse_flux_csv(rows):
    """Yield (ns, tag, field, value_text, status) from Flux CSV rows (lists of strings).
    Handles a new header per table block, blank lines, annotations and error tables."""
    idx = None
    for row in rows:
        if not row or (len(row) == 1 and not row[0]) or (row[0].startswith("#")):
            continue
        if "_time" in row and "_value" in row:
            idx = {name: i for i, name in enumerate(row)}
            continue
        if "error" in row and "reference" in row:
            idx = "error"
            continue
        if idx == "error":
            raise RuntimeError("InfluxDB reported an error: " + ",".join(row))
        if idx is None:
            continue
        yield (parse_rfc3339_ns(row[idx["_time"]]), row[idx["TagName"]], row[idx["_field"]],
               row[idx["_value"]], row[idx["S"]] if "S" in idx else "")


def friendly_error(exc, url):
    low = str(exc).lower()
    if any(k in low for k in ("connection refused", "max retries", "newconnectionerror",
                              "failed to establish", "timed out", "getaddrinfo", "name or service")):
        return (f"Cannot reach InfluxDB at {url}.\n\nCheck that the HMI PC is on, the address is correct "
                "and TCP port 8086 is open in its firewall (Public profile on non-domain PCs).")
    if "401" in low or "unauthorized" in low:
        return "The HMI PC rejected the sign-in (401). Check the token or username/password in Settings."
    if "403" in low or "forbidden" in low:
        return "The account has no read access to this data (403)."
    if "no module named" in low:
        return f"A required Python package is missing: {exc}\n\nRun: py -m pip install -r requirements.txt"
    return str(exc)[:400] + f"\n\nDetails are in {log_path()}"


class InfluxSource:
    def __init__(self, profile, general):
        from influxdb_client import InfluxDBClient

        self.url = profile_url(profile)
        self.org = profile.get("org") or "Rockwell"
        self.batch = max(1, int(general.get("batch_size", 25)))
        kwargs = dict(url=self.url, org=self.org, timeout=int(general.get("timeout_s", 120)) * 1000,
                      verify_ssl=bool(profile.get("verify_ssl")))
        if profile.get("auth") == "user":
            kwargs.update(username=profile.get("username", ""), password=profile.get("password", ""))
        else:
            kwargs["token"] = profile.get("token", "")
        self.client = InfluxDBClient(**kwargs)
        self.query_api = self.client.query_api()

    def close(self):
        try:
            self.client.close()
        except Exception:
            pass

    def ping(self):
        return self.client.ping()

    def server_version(self):
        try:
            return self.client.version()
        except Exception:
            return "unknown"

    def server_now_ns(self):
        """Current time of the HMI PC (None if it cannot be read). The log health check compares the
        last logged value with 'now'; using this PC's clock would raise false alarms when the two
        clocks differ by more than the gap tolerance."""
        try:
            for table in self._query('import "array"\narray.from(rows: [{_time: now()}])'):
                for r in table.records:
                    return dt_to_ns(r.get_time())
        except Exception:
            log.exception("Could not read the HMI PC's clock; using this PC's clock")
        return None

    def _query(self, flux):
        log.info("Flux query:\n%s", flux)
        return self.query_api.query(flux, org=self.org)

    def list_buckets(self):
        res = self.client.buckets_api().find_buckets(limit=100)
        return sorted(b.name for b in (res.buckets or []) if not b.name.startswith("_"))

    def has_tagdata(self, bucket):
        flux = ('import "influxdata/influxdb/schema"\n'
                f"schema.measurements(bucket: {flux_str(bucket)}, start: {TAG_LOOKBACK})")
        return any(r.get_value() == MEASUREMENT for t in self._query(flux) for r in t.records)

    def discover_tags(self, bucket):
        """{TagName: field} for tags logged in the last 30 days (index lookup, no data scan)."""
        parts = ['import "influxdata/influxdb/schema"']
        for field in VALUE_FIELDS:
            parts.append(f'schema.tagValues(bucket: {flux_str(bucket)}, tag: "TagName", start: {TAG_LOOKBACK}, '
                         f'predicate: (r) => r._measurement == "{MEASUREMENT}" and r._field == "{field}")'
                         f' |> yield(name: "{field}")')
        result = {}
        for table in self._query("\n".join(parts)):
            for r in table.records:
                result[r.get_value()] = r.values.get("result")
        return result

    def count_values(self, bucket, start, stop, tags):
        total = 0
        for batch in chunks(tags, self.batch):
            flux = f"""from(bucket: {flux_str(bucket)})
  |> range(start: {flux_time(start)}, stop: {flux_time(stop)})
  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}" and r._field != "{MARKER_FIELD}")
  |> filter(fn: (r) => {tag_filter(batch)})
  |> count()
  |> group()
  |> sum()"""
            for table in self._query(flux):
                for r in table.records:
                    total += int(r.get_value() or 0)
        return total

    def fetch_records(self, bucket, start, stop, tags):
        """All records (values and markers, every status) as exact text."""
        from influxdb_client import Dialect

        dialect = Dialect(header=True, delimiter=",", comment_prefix="#", annotations=[],
                          date_time_format="RFC3339Nano")
        for batch in chunks(tags, self.batch):
            flux = f"""from(bucket: {flux_str(bucket)})
  |> range(start: {flux_time(start)}, stop: {flux_time(stop)})
  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
  |> filter(fn: (r) => {tag_filter(batch)})
  |> keep(columns: ["_time", "_value", "_field", "TagName", "S"])"""
            log.info("Flux CSV query:\n%s", flux)
            yield from parse_flux_csv(self.query_api.query_csv(flux, org=self.org, dialect=dialect))

    def last_data_time(self, bucket, tags):
        flux = f"""from(bucket: {flux_str(bucket)})
  |> range(start: {TAG_LOOKBACK})
  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}" and r._field != "{MARKER_FIELD}")
  |> filter(fn: (r) => {tag_filter(tags)})
  |> last()
  |> keep(columns: ["_time"])
  |> group()
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 1)"""
        for table in self._query(flux):
            for r in table.records:
                return r.get_time()
        return None
