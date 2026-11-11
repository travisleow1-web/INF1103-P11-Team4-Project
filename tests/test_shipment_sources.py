import pytest
from io_layer.csv_source import CsvSource
from io_layer.form_source import FormSource
from io_layer.source_error import SourceError

HEADER = b"origin_port,destination_port,departure_time,arrival_time\n"
LINE = b"SGSIN,NLRTM,01/12/2026,20/12/2026\n"


def test_form_source_returns_a_copy_of_its_fields():
    fields = {"origin_port": "SGSIN"}
    rows = FormSource(fields).read()
    rows[0]["origin_port"] = "changed"
    assert fields["origin_port"] == "SGSIN"


def test_csv_source_reads_rows():
    assert CsvSource(HEADER + LINE).read() == [{"origin_port": "SGSIN", "destination_port": "NLRTM",
                                                "departure_time": "01/12/2026",
                                                "arrival_time": "20/12/2026"}]


def test_csv_source_handles_a_byte_order_mark():
    assert "origin_port" in CsvSource(b"\xef\xbb\xbf" + HEADER + LINE).read()[0]


def test_header_names_are_trimmed_and_lower_cased():
    rows = CsvSource(b"Origin_Port, destination_port ,Departure_Time,arrival_time\n"
                     b"SGSIN,NLRTM,01/12/2026,20/12/2026\n").read()
    assert set(rows[0]) == {"origin_port", "destination_port", "departure_time", "arrival_time"}


def test_a_file_with_only_a_header_is_an_error():
    with pytest.raises(SourceError, match="no shipments"):
        CsvSource(HEADER).read()


def test_an_empty_file_is_an_error():
    with pytest.raises(SourceError):
        CsvSource(b"").read()


def test_unreadable_csv_raises_source_error():
    with pytest.raises(SourceError, match="Could not read"):
        CsvSource(b"\xff\xfe\x00").read()
