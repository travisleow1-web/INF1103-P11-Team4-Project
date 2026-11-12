from logic_fixtures import NOW, PORTS, assessment, decision, factor, insight, shipment
from logic_layer.unregistered_location_rule import UnregisteredLocationRule
from model.flag import Flag


def run(a):
    d = decision()
    UnregisteredLocationRule(PORTS).apply(shipment(), a, d, NOW)
    return d


def test_registered_ports_and_general_places_are_fine():
    d = run(assessment([factor(location="SGSIN"), factor(location="Route")],
                       [insight(location="NLRTM"), insight(location="Unknown")]))
    assert d.flags == () and d.rationale == ()


def test_unregistered_locations_get_one_note_without_human_review():
    d = run(assessment([factor(location="Strait of Hormuz"), factor(location="XXABC")],
                       [insight(location="XXABC")]))
    assert d.flags == (Flag.UNREGISTERED_LOCATION,)
    assert d.rationale == ("Locations not in the port list: Strait of Hormuz, XXABC",)
    assert not d.needs_human
