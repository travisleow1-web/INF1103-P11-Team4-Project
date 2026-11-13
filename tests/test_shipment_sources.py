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


def test_many_makes_one_source_per_typed_row():
    sources = FormSource.many({"origin_port": ["SGSIN", "MYPKG"], "destination_port": ["NLRTM", "SGSIN"],
                               "departure_time": ["01/12/2026", "02/12/2026"],
                               "arrival_time": ["20/12/2026", "03/12/2026"]})
    assert [s.read()[0]["origin_port"] for s in sources] == ["SGSIN", "MYPKG"]
    assert sources[1].read()[0] == {"origin_port": "MYPKG", "destination_port": "SGSIN",
                                    "departure_time": "02/12/2026", "arrival_time": "03/12/2026"}


def test_many_skips_blank_rows_but_keeps_partly_filled_ones():
    sources = FormSource.many({"origin_port": ["", " ", "SGSIN"], "destination_port": ["", "NLRTM", ""]})
    assert [s.read()[0] for s in sources] == [{"origin_port": " ", "destination_port": "NLRTM"},
                                              {"origin_port": "SGSIN", "destination_port": ""}]


def test_many_fills_short_columns_with_blanks():
    sources = FormSource.many({"origin_port": ["SGSIN", "MYPKG"], "destination_port": ["NLRTM"]})
    assert sources[1].read()[0] == {"origin_port": "MYPKG", "destination_port": ""}


def test_many_with_no_rows_is_empty():
    assert FormSource.many({}) == []
    assert FormSource.many({"origin_port": []}) == []


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
    with pytest.raises(SourceError, match="not a readable CSV"):
        CsvSource(b"\xff\xfe\x00").read()


def test_missing_columns_are_named():
    with pytest.raises(SourceError, match="^The file is missing the columns: departure_time, arrival_time.$"):
        CsvSource(b"origin_port,destination_port\nSGSIN,NLRTM\n").read()


def test_a_text_file_that_is_not_a_csv_is_missing_every_column():
    with pytest.raises(SourceError, match="missing the columns: origin_port, destination_port"):
        CsvSource(b"hello world\nthis is not a csv\n").read()


@pytest.mark.parametrize("content", [b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff\xfe",
                                     "origin_port\n".encode("utf-16")])
def test_a_file_that_is_not_utf8_text_gets_a_plain_message(content):
    with pytest.raises(SourceError) as caught:
        CsvSource(content).read()
    assert str(caught.value) == "This file is not a readable CSV (UTF-8 text)."
