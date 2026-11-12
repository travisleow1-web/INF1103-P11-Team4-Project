from datetime import datetime, timedelta, timezone
from helpers import PORTS as DATA_PORTS, saved_record
from logic_fixtures import NOW, FakeHistory, assessment, broken_history, decision, shipment
from data_layer.json_data_manager import JsonDataManager
from logic_layer.route_history_rule import RouteHistoryRule
from logic_layer.rule_config import RuleConfig
from model.ai_assessment import AIAssessment
from model.flag import Flag
from model.risk_level import RiskLevel

RECENT = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)


def run(data, d=None, config=None, a=None):
    d = d or decision()
    RouteHistoryRule(config or RuleConfig(), data).apply(shipment(), a or assessment(), d, NOW)
    return d


def json_data(tmp_path, *records):
    data = JsonDataManager(tmp_path / "records.json", DATA_PORTS)
    for record in records:
        data.save(record)
    return data


def test_clean_history_auto_approves(tmp_path):
    d = run(json_data(tmp_path, saved_record("SHP-001", saved_at=RECENT)))
    assert not d.hold_shipment and not d.needs_human
    assert d.rationale == ("Rule 3: no flagged or delayed shipments on this route in the last 21 days",)


def test_a_flagged_record_on_the_route_needs_sign_off(tmp_path):
    d = run(json_data(tmp_path, saved_record("SHP-001", risk="HIGH", saved_at=RECENT)))
    assert d.hold_shipment and d.needs_human
    assert d.has_flag(Flag.CAUTIONARY_OVERRIDE)
    assert d.actions == ("Require human dispatcher sign-off",)


def test_a_medium_record_within_the_window_needs_sign_off(tmp_path):
    d = run(json_data(tmp_path, saved_record("SHP-001", risk="MEDIUM", saved_at=RECENT)))
    assert d.has_flag(Flag.CAUTIONARY_OVERRIDE)


def test_a_record_that_only_needed_a_human_does_not_count(tmp_path):
    d = run(json_data(tmp_path, saved_record("SHP-001", risk="LOW", outcome="ESCALATE", needs_human=True,
                                             saved_at=RECENT)))
    assert not d.has_flag(Flag.CAUTIONARY_OVERRIDE)
    assert not d.hold_shipment and not d.needs_human


def test_a_fallback_assessment_skips_the_history_check():
    history = FakeHistory()
    d = run(history, a=AIAssessment.fallback(NOW))
    assert history.calls == []
    assert d.rationale == ()


def test_a_delayed_record_on_the_route_needs_sign_off(tmp_path):
    d = run(json_data(tmp_path, saved_record("SHP-001", outcome="DELAY", saved_at=RECENT)))
    assert d.has_flag(Flag.CAUTIONARY_OVERRIDE)


def test_records_older_than_the_window_are_ignored(tmp_path):
    old = NOW - timedelta(days=22)
    d = run(json_data(tmp_path, saved_record("SHP-001", risk="HIGH", saved_at=old)))
    assert not d.has_flag(Flag.CAUTIONARY_OVERRIDE)


def test_the_window_comes_from_the_config():
    history = FakeHistory()
    run(history, config=RuleConfig(history_window_days=7))
    assert history.calls == [("SGSIN-NLRTM", NOW - timedelta(days=7))]


def test_the_rule_skips_shipments_that_are_not_low():
    history = FakeHistory()
    d = decision()
    d.raise_risk(RiskLevel.MEDIUM)
    run(history, d)
    assert history.calls == []
    assert d.rationale == ()


def test_a_storage_error_needs_a_human_instead_of_crashing():
    d = run(broken_history("database down"))
    assert d.has_flag(Flag.ROUTE_HISTORY_UNAVAILABLE)
    assert d.needs_human
    assert "database down" in d.rationale[0]
