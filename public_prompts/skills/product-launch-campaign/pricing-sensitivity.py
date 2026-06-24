"""
Pricing Elasticity Calculator
=============================

Analyzes price sensitivity by modeling demand at different price points
and computing optimal price range based on revenue and margin targets.

Inputs:
    - price_points: list of candidate prices (e.g., [29, 39, 49, 59, 79])
    - unit_cost: variable cost per unit
    - estimated_demand: dict mapping price -> estimated units sold
    - fixed_costs: monthly fixed costs (optional, default 0)

Outputs:
    - Revenue, margin, and profit for each price point
    - Recommended price range (maximizes profit within acceptable margin)
    - Visualization-ready data structure

Dependencies: Python 3.8+ standard library only (no pip installs)

Example:
    price_points = [29, 39, 49, 59, 79]
    estimated_demand = {29: 5000, 39: 3800, 49: 2600, 59: 1600, 79: 700}
    unit_cost = 8.50
    fixed_costs = 15000
"""

import json
import statistics
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass
class PriceAnalysis:
    price: float
    units: int
    revenue: float
    total_cost: float
    gross_profit: float
    gross_margin_pct: float
    net_profit: float
    net_margin_pct: float


@dataclass
class PricingRecommendation:
    optimal_price: float
    optimal_profit: float
    recommended_range_low: float
    recommended_range_high: float
    rationale: str


def calculate_elasticity(price_points: List[float],
                         estimated_demand: Dict[float, int]) -> List[float]:
    """Compute price elasticity of demand between consecutive price points."""
    elasticities = []
    sorted_prices = sorted(price_points)
    for i in range(1, len(sorted_prices)):
        p1, p2 = sorted_prices[i - 1], sorted_prices[i]
        q1, q2 = estimated_demand[p1], estimated_demand[p2]
        pct_change_q = (q2 - q1) / q1 if q1 != 0 else 0
        pct_change_p = (p2 - p1) / p1 if p1 != 0 else 0
        elasticity = pct_change_q / pct_change_p if pct_change_p != 0 else 0
        elasticities.append(round(elasticity, 3))
    return elasticities


def analyze_price_points(price_points: List[float],
                         estimated_demand: Dict[float, int],
                         unit_cost: float,
                         fixed_costs: float = 0) -> List[PriceAnalysis]:
    """Analyze revenue, cost, and profit at each price point."""
    results = []
    for price in sorted(price_points):
        units = estimated_demand.get(price, 0)
        revenue = price * units
        variable_cost = unit_cost * units
        total_cost = variable_cost + fixed_costs
        gross_profit = revenue - variable_cost
        gross_margin_pct = (gross_profit / revenue * 100) if revenue > 0 else 0
        net_profit = revenue - total_cost
        net_margin_pct = (net_profit / revenue * 100) if revenue > 0 else 0
        results.append(PriceAnalysis(
            price=price,
            units=units,
            revenue=round(revenue, 2),
            total_cost=round(total_cost, 2),
            gross_profit=round(gross_profit, 2),
            gross_margin_pct=round(gross_margin_pct, 1),
            net_profit=round(net_profit, 2),
            net_margin_pct=round(net_margin_pct, 1),
        ))
    return results


def recommend_price(analyses: List[PriceAnalysis],
                    min_margin_pct: float = 20.0) -> PricingRecommendation:
    """Recommend optimal price and acceptable range."""
    viable = [a for a in analyses if a.gross_margin_pct >= min_margin_pct]
    if not viable:
        viable = analyses

    best = max(viable, key=lambda a: a.net_profit)
    profitable = [a for a in viable if a.net_profit > 0]

    if len(profitable) >= 2:
        range_low = min(a.price for a in profitable)
        range_high = max(a.price for a in profitable)
    else:
        range_low = best.price
        range_high = best.price

    rationale = (
        f"Price ${best.price} maximizes net profit at ${best.net_profit:,.2f} "
        f"with {best.gross_margin_pct}% gross margin and {best.units:,} units. "
        f"Viable range ${range_low}-${range_high} maintains >{min_margin_pct}% margin."
    )

    return PricingRecommendation(
        optimal_price=best.price,
        optimal_profit=best.net_profit,
        recommended_range_low=range_low,
        recommended_range_high=range_high,
        rationale=rationale,
    )


def format_report(analyses: List[PriceAnalysis],
                  elasticities: List[float],
                  recommendation: PricingRecommendation) -> str:
    """Format a human-readable pricing report."""
    lines = ["=" * 60, "PRICING SENSITIVITY ANALYSIS", "=" * 60, ""]
    header = f"{'Price':>8} {'Units':>8} {'Revenue':>12} {'Gross %':>8} {'Net Profit':>12}"
    lines.append(header)
    lines.append("-" * 60)
    for a in analyses:
        lines.append(
            f"${a.price:>7.2f} {a.units:>8,} ${a.revenue:>11,.2f} "
            f"{a.gross_margin_pct:>7.1f}% ${a.net_profit:>11,.2f}"
        )
    lines.append("")
    lines.append("Price Elasticity Between Points:")
    sorted_prices = sorted(a.price for a in analyses)
    for i, e in enumerate(elasticities):
        lines.append(f"  ${sorted_prices[i]} -> ${sorted_prices[i+1]}: {e}")
    lines.append("")
    lines.append("RECOMMENDATION")
    lines.append("-" * 60)
    lines.append(recommendation.rationale)
    lines.append(f"  Optimal price:    ${recommendation.optimal_price}")
    lines.append(f"  Suggested range:  ${recommendation.recommended_range_low} - "
                 f"${recommendation.recommended_range_high}")
    lines.append("=" * 60)
    return "\n".join(lines)


def run_analysis(price_points: List[float],
                 estimated_demand: Dict[float, int],
                 unit_cost: float,
                 fixed_costs: float = 0,
                 min_margin_pct: float = 20.0) -> dict:
    """Run full analysis and return structured results plus report text."""
    analyses = analyze_price_points(price_points, estimated_demand,
                                    unit_cost, fixed_costs)
    elasticities = calculate_elasticity(price_points, estimated_demand)
    recommendation = recommend_price(analyses, min_margin_pct)
    report = format_report(analyses, elasticities, recommendation)

    return {
        "analyses": [asdict(a) for a in analyses],
        "elasticities": elasticities,
        "recommendation": asdict(recommendation),
        "report_text": report,
    }


if __name__ == "__main__":
    # Example: SaaS product pricing analysis
    price_points = [29, 39, 49, 59, 79]
    estimated_demand = {29: 5000, 39: 3800, 49: 2600, 59: 1600, 79: 700}
    unit_cost = 8.50
    fixed_costs = 15000

    result = run_analysis(price_points, estimated_demand, unit_cost, fixed_costs)
    print(result["report_text"])
    print("\nJSON output:")
    print(json.dumps(result["recommendation"], indent=2))
