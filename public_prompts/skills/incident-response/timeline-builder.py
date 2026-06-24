"""
Incident Timeline Builder

Parses timestamped log lines into a chronological incident timeline
with gap detection. Helps reconstruct what happened during an incident
for postmortem analysis.

Inputs:
    Paste log lines into the LOG_DATA string below, or read from a file
    by setting LOG_FILE. Supports common timestamp formats:
    - 2024-01-15T14:32:01Z (ISO 8601)
    - 2024-01-15 14:32:01.123 (datetime with millis)
    - Jan 15 14:32:01 (syslog)
    - 14:32:01 (time only, assumes today)

Outputs:
    - Chronological timeline with duration between events
    - Gap detection (periods >60s with no events)
    - Summary statistics

Dependencies: None (standard library only)
"""

import re
from datetime import datetime, timedelta

# ── Configuration ───────────────────────────────────────────────────────

GAP_THRESHOLD_SECONDS = 60  # Flag gaps longer than this

LOG_FILE = None  # Set to a file path to read from file instead of LOG_DATA

LOG_DATA = """
2024-01-15T14:30:01Z [monitoring] Alert triggered: API latency p99 > 2000ms
2024-01-15T14:30:15Z [pagerduty] Page sent to on-call engineer
2024-01-15T14:31:02Z [slack] IC acknowledged incident in #incidents
2024-01-15T14:32:30Z [engineer] Checking API gateway logs - seeing connection pool exhaustion
2024-01-15T14:33:45Z [engineer] Database connections at 95% capacity (max 100)
2024-01-15T14:34:00Z [engineer] Identified: background job spike causing connection leak
2024-01-15T14:35:30Z [engineer] Killing runaway background workers
2024-01-15T14:36:00Z [monitoring] Connection pool dropping: 95% -> 60%
2024-01-15T14:38:00Z [monitoring] API latency p99 back to normal (<200ms)
2024-01-15T14:40:00Z [IC] Incident resolved, monitoring for recurrence
2024-01-15T14:55:00Z [IC] All clear - marking incident as resolved
""".strip()


# ── Timestamp parsing ───────────────────────────────────────────────────

TIMESTAMP_PATTERNS = [
    (r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?", "%Y-%m-%dT%H:%M:%S"),
    (r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+", "%Y-%m-%d %H:%M:%S"),
    (r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", "%Y-%m-%d %H:%M:%S"),
    (r"[A-Z][a-z]{2} \d{1,2} \d{2}:\d{2}:\d{2}", None),  # syslog
    (r"\d{2}:\d{2}:\d{2}", None),  # time only
]


def parse_timestamp(line):
    for pattern, fmt in TIMESTAMP_PATTERNS:
        match = re.search(pattern, line)
        if match:
            ts_str = match.group().rstrip("Z")
            if fmt:
                try:
                    return datetime.strptime(ts_str, fmt)
                except ValueError:
                    ts_str_no_ms = ts_str.split(".")[0]
                    return datetime.strptime(ts_str_no_ms, fmt)
            elif ":" in ts_str and len(ts_str) <= 8:
                today = datetime.now().strftime("%Y-%m-%d")
                return datetime.strptime(f"{today} {ts_str}", "%Y-%m-%d %H:%M:%S")
    return None


def parse_source(line):
    match = re.search(r"\[(\w+)\]", line)
    return match.group(1) if match else "unknown"


def clean_message(line):
    line = re.sub(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[Z.]?\d*\s*", "", line)
    line = re.sub(r"^\[\w+\]\s*", "", line)
    return line.strip()


# ── Analysis ────────────────────────────────────────────────────────────

def build_timeline(log_text):
    events = []
    for line in log_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        ts = parse_timestamp(line)
        if ts is None:
            continue
        events.append({
            "timestamp": ts,
            "source": parse_source(line),
            "message": clean_message(line),
            "raw": line,
        })

    events.sort(key=lambda e: e["timestamp"])
    return events


def detect_gaps(events, threshold_seconds):
    gaps = []
    for i in range(1, len(events)):
        delta = (events[i]["timestamp"] - events[i - 1]["timestamp"]).total_seconds()
        if delta > threshold_seconds:
            gaps.append({
                "after_event": i - 1,
                "before_event": i,
                "gap_seconds": delta,
                "from_time": events[i - 1]["timestamp"],
                "to_time": events[i]["timestamp"],
            })
    return gaps


def print_timeline(events, gaps):
    print("=" * 80)
    print("INCIDENT TIMELINE")
    print("=" * 80)
    print()

    gap_indices = {g["before_event"] for g in gaps}
    prev_ts = None

    for i, event in enumerate(events):
        if i in gap_indices:
            gap = next(g for g in gaps if g["before_event"] == i)
            mins = gap["gap_seconds"] / 60
            print(f"  {'':>12}  ⚠️  GAP: {mins:.1f} minutes with no events")
            print()

        delta_str = ""
        if prev_ts:
            delta = (event["timestamp"] - prev_ts).total_seconds()
            if delta < 60:
                delta_str = f"+{delta:.0f}s"
            else:
                delta_str = f"+{delta / 60:.1f}m"

        ts_str = event["timestamp"].strftime("%H:%M:%S")
        print(f"  {ts_str}  {delta_str:>6}  [{event['source']:>12}]  {event['message']}")
        prev_ts = event["timestamp"]

    if events:
        total = (events[-1]["timestamp"] - events[0]["timestamp"]).total_seconds()
        print()
        print("-" * 80)
        print(f"Total duration: {total / 60:.1f} minutes")
        print(f"Events recorded: {len(events)}")
        print(f"Gaps detected (>{GAP_THRESHOLD_SECONDS}s): {len(gaps)}")

        sources = {}
        for e in events:
            sources[e["source"]] = sources.get(e["source"], 0) + 1
        print(f"Sources: {', '.join(f'{k}({v})' for k, v in sorted(sources.items()))}")


if __name__ == "__main__":
    log_text = LOG_DATA
    if LOG_FILE:
        with open(LOG_FILE) as f:
            log_text = f.read()

    events = build_timeline(log_text)
    if not events:
        print("No timestamped events found in log data.")
    else:
        gaps = detect_gaps(events, GAP_THRESHOLD_SECONDS)
        print_timeline(events, gaps)
