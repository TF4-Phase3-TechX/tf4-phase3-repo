import csv, re, sys
from pathlib import Path
stats, history = map(Path, sys.argv[1:3])
if not stats.is_file() or not history.is_file(): raise SystemExit("FAIL: stats and stats-history CSV are required")
rows = list(csv.DictReader(stats.open(encoding="utf-8-sig")))
def count(pattern):
    matched = [r for r in rows if re.search(pattern, r.get("Name", ""), re.I)]
    return sum(int(float(r.get("Request Count") or r.get("# requests") or r.get("Requests") or 0)) for r in matched)
failed = False
for flow, pattern, minimum in (("Browse", r"browse|home|product|recommend", 1000), ("Cart", r"cart", 500), ("Checkout", r"checkout", 200)):
    actual=count(pattern); print(f"{flow}: {actual} (minimum {minimum})"); failed |= actual < minimum
print("Timestamped before/during/after and ±2-minute guards must be evaluated from named flow rows in stats-history.csv.")
if failed: raise SystemExit("FAIL: aggregate volume guard not met")
