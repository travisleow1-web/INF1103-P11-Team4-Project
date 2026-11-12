from datetime import date, datetime, timezone
from helpers import saved_record
from model.search_criteria import SearchCriteria


def test_no_filters_match_everything():
    assert SearchCriteria().matches(saved_record())


def test_each_filter_matches_and_rejects():
    r = saved_record(risk="HIGH", outcome="ESCALATE", needs_human=True)
    assert SearchCriteria(shipment_id="SHP-001").matches(r)
    assert not SearchCriteria(shipment_id="SHP-002").matches(r)
    assert SearchCriteria(origin="SGSIN", destination="NLRTM").matches(r)
    assert not SearchCriteria(origin="NLRTM").matches(r)
    assert not SearchCriteria(destination="SGSIN").matches(r)
    assert SearchCriteria(overall_risk="HIGH").matches(r)
    assert not SearchCriteria(overall_risk="LOW").matches(r)
    assert SearchCriteria(outcome="ESCALATE").matches(r)
    assert not SearchCriteria(outcome="PROCEED").matches(r)
    assert SearchCriteria(needs_human=True).matches(r)
    assert not SearchCriteria(needs_human=False).matches(r)


def test_all_filters_must_pass_together():
    r = saved_record(risk="HIGH")
    assert not SearchCriteria(origin="SGSIN", overall_risk="LOW").matches(r)


def test_risk_and_outcome_ignore_case():
    r = saved_record(risk="Low", outcome="PROCEED")
    assert SearchCriteria(overall_risk="LOW", outcome="proceed").matches(r)


def test_needs_human_false_is_a_real_filter():
    assert SearchCriteria(needs_human=False).matches(saved_record(needs_human=False))
    assert not SearchCriteria(needs_human=False).matches(saved_record(needs_human=True))


def test_departure_range_is_inclusive():
    r = saved_record(departure=date(2026, 12, 10))
    assert SearchCriteria(departure_from=date(2026, 12, 10), departure_to=date(2026, 12, 10)).matches(r)
    assert not SearchCriteria(departure_from=date(2026, 12, 11)).matches(r)
    assert not SearchCriteria(departure_to=date(2026, 12, 9)).matches(r)


def test_query_uses_the_decision_prefix_and_real_dates():
    query = SearchCriteria(shipment_id="shp-001", origin="sgsin", overall_risk="High", outcome="INSURE",
                           needs_human=False, departure_from=date(2026, 12, 1),
                           departure_to=date(2026, 12, 31)).to_query()
    assert query["shipment_id"] == "SHP-001"
    assert query["origin"] == "SGSIN"
    assert query["decision.overall_risk"]["$options"] == "i"
    assert "decision.outcome" in query
    assert query["decision.needs_human"] is False
    assert query["departure"] == {"$gte": datetime(2026, 12, 1, tzinfo=timezone.utc),
                                  "$lte": datetime(2026, 12, 31, tzinfo=timezone.utc)}
    assert "overall_risk" not in query                  # the old bug: filtering the wrong level


def test_query_with_no_filters_is_empty():
    assert SearchCriteria().to_query() == {}
