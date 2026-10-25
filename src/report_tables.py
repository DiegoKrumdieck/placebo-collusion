"""Report tables from existing result files only (no API calls, no new runs).

Writes:
- results/followup/holdback_per_game_report.csv: every Haiku hold-back game (baseline, instructed,
  strategy-instructed) with its 202-220 category and deepest cut, and its 202-260 category for the
  12 games extended to period 260 (report Table A2).
- results/followup/holdback_report_counts.csv: hold-back category counts per row for the
  pre-registered window (202-220) and for the report's window (202-260 where extended), plus Fisher's
  exact test for punish-and-return, Haiku baseline vs strategy-instructed (report Table 3, Section 4.4).
"""
import csv
import math
from collections import Counter
from pathlib import Path

FU = Path(__file__).parent.parent / "results" / "followup"
CATS = ["no reaction", "matching", "punish-and-return", "persistent", "other"]


def read(name):
    with open(FU / name, newline="") as f:
        return list(csv.DictReader(f))


def fisher_two_sided(a, b, c, d):
    """Two-sided Fisher exact p for [[a, b], [c, d]]: sum of tables at most as likely as the observed one."""
    r1, r2, c1, n = a + b, c + d, a + c, a + b + c + d
    def prob(x):
        return math.comb(r1, x) * math.comb(r2, c1 - x) / math.comb(n, c1)
    p_obs = prob(a)
    lo, hi = max(0, c1 - r2), min(r1, c1)
    return sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= p_obs * (1 + 1e-9))


haiku = read("haiku_holdback_per_game.csv") + read("strategy_holdback_per_game.csv")
ext = {r["run_id"]: r for r in read("extension_per_game.csv")}

per_game = []
for r in haiku:
    e = ext.get(r["run_id"])
    per_game.append({
        "row": r["row"], "run_id": r["run_id"], "p0_200": r["p0_200"],
        "category_202_220": r["category"], "min_D_202_220": r["min_D"], "D_220": r["D_220"],
        "category_202_260": e["category_202_260"] if e else "",
        "first_back_after_220": e["first_back_after_220"] if e else "",
        "D_260": e["D_260"] if e else "", "min_D_202_260": e["min_D"] if e else "",
        "report_category": e["category_202_260"] if e else r["category"],
    })
with open(FU / "holdback_per_game_report.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(per_game[0]))
    w.writeheader()
    w.writerows(per_game)

counts = []
def add(row, window, cats):
    c = Counter(cats)
    counts.append({"row": row, "window": window, "n_games": len(cats), **{k: c.get(k, 0) for k in CATS}})

for row in ["Haiku baseline", "Haiku instructed", "Haiku strategy-instructed"]:
    g = [p for p in per_game if p["row"] == row]
    add(row, "202-220", [p["category_202_220"] for p in g])
    add(row, "202-260 where extended", [p["report_category"] for p in g])

synth = read("synthetic_holdback_per_game.csv") + read("noisy_holdback_per_game.csv")
for row in sorted({r["row"] for r in synth}):
    add(row, "202-220", [r["category"] for r in synth if r["row"] == row])
l10 = [r for r in ext.values() if r["row"] == "noisy colluder L=10"]
add("noisy colluder L=10", "202-260 where extended", [r["category_202_260"] for r in l10])

def pr(row, window):
    c = next(x for x in counts if x["row"] == row and x["window"] == window)
    return c["punish-and-return"], c["n_games"] - c["punish-and-return"]

for window in ["202-220", "202-260 where extended"]:
    a, b = pr("Haiku baseline", window)
    c, d = pr("Haiku strategy-instructed", window)
    counts.append({"row": "Fisher exact p, punish-and-return: baseline vs strategy-instructed", "window": window,
                   "n_games": a + b + c + d, "no reaction": "", "matching": "",
                   "punish-and-return": round(fisher_two_sided(a, b, c, d), 4), "persistent": "", "other": ""})

with open(FU / "holdback_report_counts.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(counts[0]))
    w.writeheader()
    w.writerows(counts)
print("wrote", FU / "holdback_per_game_report.csv", "and", FU / "holdback_report_counts.csv")
