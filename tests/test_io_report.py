"""IOManager.show_report: the counts and sentences behind the summary at the top of the results page."""
from datetime import date, datetime, timezone
from helpers import FETCHED_AT, FakeData, make_io, saved_record
from model.ai_assessment import AIAssessment
from model.ai_status import AIStatus
from model.risk_factor import RiskFactor
from model.risk_level import RiskLevel
from model.risk_type import RiskType
from model.shipment_record import ShipmentRecord

SAVED = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)        # saved_record's default time
NEW_DATES = (date(2026, 11, 8), date(2026, 11, 13), "Clear soon")


def high_weather(record: ShipmentRecord) -> ShipmentRecord:
    """The same record, but its AI assessment has a High weather risk (so only the dates can explain no suggestion)."""
    factor = RiskFactor(RiskType.WEATHER, RiskLevel.HIGH, "NLRTM", "open_meteo_weather", "wind_gusts_10m=80")
    assessment = AIAssessment([factor], [], RiskType.WEATHER, "NLRTM", "Delay", 0.9, False, AIStatus.LIVE, FETCHED_AT)
    return ShipmentRecord(record.shipment, assessment, record.decision, record.saved_at)


def report(*records, **options):
    return make_io(FakeData()).show_report(list(records), **options)


def test_counts_by_risk_and_outcome_in_a_fixed_order_with_shares():
    result = report(saved_record("SHP-001", risk="LOW"), saved_record("SHP-002", risk="LOW"),
                    saved_record("SHP-003", risk="HIGH", outcome="DELAY"),
                    saved_record("SHP-004", risk="EXTREME", outcome="REJECT"))
    assert [(r["label"], r["count"]) for r in result["risk"]] == [("Low", 2), ("Medium", 0), ("High", 1), ("Extreme", 1)]
    assert [(o["label"], o["count"]) for o in result["outcome"]] == [
        ("Proceed", 2), ("Delay", 1), ("Insure", 0), ("Escalate", 0), ("Reject", 1)]
    assert result["risk"][0]["share"] == 50.0
    assert result["assessed"] == 4 and result["high_or_extreme"] == 2


def test_counts_people_to_check_and_shipments_the_ai_could_not_assess():
    result = report(saved_record("SHP-001"), saved_record("SHP-002", needs_human=True),
                    saved_record("SHP-003", fallback=True, needs_human=True))
    assert result["needs_human"] == 2
    assert result["ai_unavailable"] == 1 and result["ai_unavailable_ids"] == ["SHP-003"]


def test_an_empty_run_is_all_zeros():
    result = report()
    assert result["assessed"] == 0 and result["suggested"] == 0 and result["no_date"] is None
    assert all(r["share"] == 0 for r in result["risk"])


def test_dates_suggested_and_none_are_counted_for_high_risk_only():
    result = report(saved_record("SHP-001", risk="MEDIUM"),
                    saved_record("SHP-002", risk="HIGH", reschedule=NEW_DATES),
                    saved_record("SHP-003", risk="HIGH", reschedule=NEW_DATES))
    assert result["high_total"] == 2 and result["suggested"] == 2
    assert result["no_date"] is None                                 # nobody is missing a date


def test_no_date_because_it_had_already_left():
    left = saved_record("SHP-001", risk="HIGH", departure=date(2026, 10, 20), arrival=date(2026, 10, 27))
    assert report(left)["no_date"] == "1 has none because it had already left."


def test_no_date_because_the_arrival_is_after_the_forecast():
    far = saved_record("SHP-001", risk="HIGH")                      # arrives 28/12, saved 01/11: past a 16-day forecast
    assert report(far)["no_date"] == "1 has none because its arrival is after the 16-day forecast."


def test_the_forecast_length_comes_from_the_manager_not_a_fixed_number():
    far = saved_record("SHP-001", risk="HIGH", departure=date(2026, 11, 3), arrival=date(2026, 11, 20))
    assert report(far)["no_date"] == "1 has none because its arrival is after the 16-day forecast."
    from helpers import PORTS
    from io_layer.io_manager import IOManager
    from io_layer.shipment_validator import ShipmentValidator
    long_forecast = IOManager(ShipmentValidator(PORTS), FakeData(), PORTS, forecast_days=30)
    assert "no clear day" in long_forecast.show_report([high_weather(far)])["no_date"]


def test_no_date_because_the_risk_is_not_weather():
    near = saved_record("SHP-001", risk="HIGH", departure=date(2026, 11, 3), arrival=date(2026, 11, 8))
    assert report(near)["no_date"] == "1 has none because its risk is not a weather problem."


def test_no_date_because_no_clear_day_was_found():
    near = high_weather(saved_record("SHP-001", risk="HIGH", departure=date(2026, 11, 3), arrival=date(2026, 11, 8)))
    assert report(near)["no_date"] == "1 has none because no clear day was found in the forecast."


def test_several_reasons_share_one_sentence():
    left = saved_record("SHP-001", risk="HIGH", departure=date(2026, 10, 20), arrival=date(2026, 10, 27))
    far = saved_record("SHP-002", risk="HIGH")
    far2 = saved_record("SHP-003", risk="EXTREME")
    text = report(left, far, far2)["no_date"]
    assert text == ("3 have none: 1 because it had already left; "
                    "2 because their arrivals are after the 16-day forecast.")


def test_several_shipments_with_the_same_reason_get_one_plural_sentence():
    left = [saved_record(f"SHP-00{n}", risk="HIGH", departure=date(2026, 10, 20), arrival=date(2026, 10, 27))
            for n in (1, 2)]
    assert report(*left)["no_date"] == "2 have none because they had already left."


def test_run_facts_are_shown_in_singapore_time_and_plain_units():
    finished = datetime(2026, 11, 15, 16, 31, tzinfo=timezone.utc)
    result = report(saved_record("SHP-001"), not_saved=1, planned=5, seconds=102, finished_at=finished)
    assert result["finished_at"] == "16/11/2026 00:31 SGT" and result["took"] == "1 min 42 s"
    assert result["saved"] == 0 and result["not_saved"] == 1
    assert result["stopped"] == "Stopped after 1 of 5 shipments."
    quick = report(saved_record("SHP-001"), seconds=42.4)
    assert quick["took"] == "42 s" and quick["stopped"] is None and quick["finished_at"] is None
