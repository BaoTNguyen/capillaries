"""
Budget vs Actual Variance Analyzer

Compares budget targets to actual results, flags statistically significant
variances, and outputs a formatted summary for QBR preparation.

Inputs:
    Modify the BUDGET and ACTUAL dictionaries below with your data.
    Each key is a metric name, value is the dollar amount or numeric value.

Outputs:
    - Variance table with absolute and percentage differences
    - Flagged items exceeding the significance threshold
    - Summary statistics

Dependencies: None (standard library only)
"""

import statistics

# ── Configuration ───────────────────────────────────────────────────────

SIGNIFICANCE_THRESHOLD = 0.10  # Flag variances > 10%

# Replace with your actual data
BUDGET = {
    "Revenue": 4_000_000,
    "COGS": 1_200_000,
    "Gross Margin": 2_800_000,
    "Sales & Marketing": 800_000,
    "R&D": 1_000_000,
    "G&A": 400_000,
    "Operating Income": 600_000,
    "Headcount": 85,
    "Customer Count": 340,
    "ARR": 16_000_000,
    "Net Revenue Retention": 1.15,
    "CAC": 12_000,
}

ACTUAL = {
    "Revenue": 4_480_000,
    "COGS": 1_350_000,
    "Gross Margin": 3_130_000,
    "Sales & Marketing": 920_000,
    "R&D": 1_050_000,
    "G&A": 380_000,
    "Operating Income": 780_000,
    "Headcount": 92,
    "Customer Count": 365,
    "ARR": 17_200_000,
    "Net Revenue Retention": 1.18,
    "CAC": 14_500,
}

# Metrics where HIGHER actual is WORSE (costs, expenses)
INVERSE_METRICS = {"COGS", "Sales & Marketing", "R&D", "G&A", "Headcount", "CAC"}


# ── Analysis ────────────────────────────────────────────────────────────

def analyze_variances(budget, actual, threshold):
    results = []
    for metric in budget:
        if metric not in actual:
            continue
        b, a = budget[metric], actual[metric]
        if b == 0:
            continue

        abs_var = a - b
        pct_var = abs_var / abs(b)
        is_inverse = metric in INVERSE_METRICS
        favorable = (abs_var > 0) if not is_inverse else (abs_var < 0)
        flagged = abs(pct_var) >= threshold

        results.append({
            "metric": metric,
            "budget": b,
            "actual": a,
            "abs_variance": abs_var,
            "pct_variance": pct_var,
            "favorable": favorable,
            "flagged": flagged,
        })
    return results


def format_value(metric, value):
    if isinstance(value, float) and value < 10:
        return f"{value:.2f}"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.0f}K" if metric not in {"Headcount", "Customer Count"} else f"{value:,.0f}"
    return f"{value:,.0f}"


def print_report(results):
    print("=" * 80)
    print("BUDGET vs ACTUAL VARIANCE ANALYSIS")
    print("=" * 80)
    print()
    print(f"{'Metric':<25} {'Budget':>12} {'Actual':>12} {'Variance':>12} {'%':>8} {'Status':>10}")
    print("-" * 80)

    flagged_items = []
    for r in results:
        status = "+" if r["favorable"] else "-"
        flag = " ***" if r["flagged"] else ""
        print(
            f"{r['metric']:<25} "
            f"{format_value(r['metric'], r['budget']):>12} "
            f"{format_value(r['metric'], r['actual']):>12} "
            f"{format_value(r['metric'], abs(r['abs_variance'])):>12} "
            f"{r['pct_variance']:>+7.1%} "
            f"{'FAVORABLE' if r['favorable'] else 'UNFAVORABLE':>10}"
            f"{flag}"
        )
        if r["flagged"]:
            flagged_items.append(r)

    print()
    print(f"Significance threshold: {SIGNIFICANCE_THRESHOLD:.0%}")
    print(f"Metrics analyzed: {len(results)}")
    print(f"Flagged variances (>{SIGNIFICANCE_THRESHOLD:.0%}): {len(flagged_items)}")

    if flagged_items:
        print()
        print("FLAGGED ITEMS REQUIRING EXPLANATION:")
        print("-" * 40)
        for r in flagged_items:
            direction = "over" if r["abs_variance"] > 0 else "under"
            sentiment = "favorably" if r["favorable"] else "unfavorably"
            print(f"  - {r['metric']}: {direction} by {abs(r['pct_variance']):.1%} ({sentiment})")

    pct_variances = [abs(r["pct_variance"]) for r in results]
    print()
    print(f"Average absolute variance: {statistics.mean(pct_variances):.1%}")
    print(f"Max variance: {max(pct_variances):.1%}")


if __name__ == "__main__":
    results = analyze_variances(BUDGET, ACTUAL, SIGNIFICANCE_THRESHOLD)
    print_report(results)
