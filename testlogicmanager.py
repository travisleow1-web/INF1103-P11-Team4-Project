from datetime import datetime, timedelta

import logic_manager

NOW = datetime(2026, 9, 28, 9, 0)  # fixed "current time" so results are the same on every run

# A clean AI row for SGSIN -> NLRTM; each scenario changes only what it needs.
BASE = {
    "shipment_id": "SHP-001", "origin_port": "SGSIN", "origin_lat": 1.266667, "origin_lon": 103.833333,
    "destination_port": "NLRTM", "destination_lat": 51.933333, "destination_lon": 4.133333,
    "departure_time": "01/10/2026", "arrival_time": "30/10/2026",
    "risk_factors": [], "primary_risk_factor": "weather", "affected_location": "Strait of Malacca",
    "expected_impact": "Delay", "confidence_score": 0.82, "sources": ["open_meteo_weather", "gdelt_news"],
    "conflicting_sources": False, "insights": [],
    "external_data_fetched_at": (NOW - timedelta(hours=1)).isoformat(),
}

# Route history in the same shape data_manager saves: SGSIN-NLRTM was delayed 10 days ago.
HISTORY = [{"route_id": "SGSIN-NLRTM", "saved_at": (NOW - timedelta(days=10)).isoformat(),
            "flagged": False, "delayed": True}]


def factor(risk_type, severity, detail="-"):
    """One AI risk factor, as ai_manager returns it."""
    return {"type": risk_type, "severity": severity, "detail": detail}


def insight(code, risk_type, severity, location="Route", days=0):
    """One AI insight flag, as ai_manager returns it."""
    return {"code": code, "risk_type": risk_type, "severity": severity, "location": location,
            "estimated_delay_days": days}


# name: (AI row, expected outcome, expected overall risk, flags that must appear)
SCENARIOS = {
    "Clean low-risk route, no history": (
        {**BASE, "origin_port": "CNSHA", "destination_port": "SGSIN", "affected_location": "CNSHA",
         "risk_factors": [factor("weather", "Low", "wind_gust_kmh=15")]},
        "PROCEED", "Low", []),
    "Medium risk proceeds with monitoring": (
        {**BASE, "origin_port": "CNSHA", "destination_port": "SGSIN",
         "risk_factors": [factor("port_congestion", "Medium", "news_articles=2")]},
        "PROCEED", "Medium", []),
    "Rule 1: Perfect Storm (3 Mediums)": (
        {**BASE, "risk_factors": [factor("weather", "Medium", "wind_gust_kmh=55"),
                                  factor("port_congestion", "Medium", "news_articles=3"),
                                  factor("labor_shortage", "Medium", "news_articles=2")]},
        "DELAY", "High", ["Perfect Storm"]),
    "Rule 1b: AI expects an 8-day delay": (
        {**BASE, "origin_port": "CNSHA", "destination_port": "SGSIN",
         "insights": [insight("POTENTIAL_DELAY", "weather", "High", "CNSHA", 8)]},
        "DELAY", "High", ["Significant Delay Expected"]),
    "Rule 3: Low risk but bad route history": (
        {**BASE, "risk_factors": [factor("weather", "Low", "wind_gust_kmh=20")]},
        "ESCALATE", "Low", ["Cautionary Override"]),
    "Rule 4: Piracy needs insurance": (
        {**BASE, "primary_risk_factor": "piracy_threat", "affected_location": "Singapore Strait",
         "risk_factors": [factor("piracy_threat", "High", "news_articles=4")]},
        "INSURE", "High", ["Premium Increase Required"]),
    "Rule 5: Cargo destruction at origin": (
        {**BASE, "origin_port": "CNSHA", "destination_port": "SGSIN", "affected_location": "CNSHA",
         "expected_impact": "Cargo Destruction",
         "risk_factors": [factor("weather", "High", "wind_gust_kmh=180")],
         "insights": [insight("MULTIPLE_RISKS", "weather", "High", "CNSHA", 10)]},
        "DELAY", "High", ["Procurement Alert", "Compound Risk"]),
    "AI failed (fallback response)": (
        {**BASE, "origin_port": "CNSHA", "destination_port": "SGSIN", "sources": [], "confidence_score": 0.0,
         "conflicting_sources": True, "primary_risk_factor": "infrastructure_disruption",
         "affected_location": "Unknown", "expected_impact": "None",
         "insights": [insight("MISSING_DATA", "none", "High")]},
        "ESCALATE", "Low", ["Low AI confidence", "AI flagged: MISSING_DATA"]),
    "AI returned free text instead of codes": (
        {**BASE, "origin_port": "CNSHA", "destination_port": "SGSIN", "affected_location": "near Shanghai port",
         "insights": ["Typhoon may cause delays."]},
        "ESCALATE", "Low", ["AI output outside schema"]),
    "Invalid confidence score": (
        {**BASE, "confidence_score": 95},
        "REJECT", "Low", ["Invalid confidence score"]),
    "Incomplete AI record": (
        {"shipment_id": "SHP-011"},
        "REJECT", "Low", ["Incomplete AI record"]),
}


def run_scenario(name):
    """Run one scenario; return (decision, list of problems). An empty list means it passed."""
    record, outcome, risk, flags = SCENARIOS[name]
    _, d = logic_manager.evaluate_shipment(record, HISTORY, NOW)
    problems = []
    if d["outcome"] != outcome:
        problems.append(f"outcome {d['outcome']}, expected {outcome}")
    if d["overall_risk"] != risk:
        problems.append(f"risk {d['overall_risk']}, expected {risk}")
    problems += [f"missing flag '{f}'" for f in flags if f not in d["flags"]]
    return d, problems


def test_scenarios():
    """pytest entry point: every scenario must give its expected result."""
    failures = {name: run_scenario(name)[1] for name in SCENARIOS}
    assert not any(failures.values()), {n: p for n, p in failures.items() if p}


if __name__ == "__main__":
    passed = 0
    for name in SCENARIOS:
        d, problems = run_scenario(name)
        passed += not problems
        print(f"\n[{'PASS' if not problems else 'FAIL'}] {name}")
        print(f"  Outcome: {d['outcome']} | Risk: {d['overall_risk']} | Human review: {d['needs_human']}")
        print(f"  Flags  : {d['flags']}")
        for reason in d["rationale"]:
            print(f"    - {reason}")
        for problem in problems:
            print(f"  !! {problem}")
    print(f"\n{passed}/{len(SCENARIOS)} scenarios passed")