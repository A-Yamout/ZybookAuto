from section_numbers import section_number


def test_prefers_discrete_number_over_canonical_decimal_string():
    assert section_number({"number": 10, "canonical_section_number": "1.10"}, 1) == 10
    assert section_number({"number": 11, "canonical_section_number": "1.11"}, 1) == 11


def test_parses_canonical_number_when_number_is_missing():
    assert section_number({"canonical_section_number": "1.10"}, 1) == 10
    assert section_number({"canonical_section_number": "2.11"}, 2) == 11


def test_plain_section_numbers_still_work():
    assert section_number({"number": 9, "canonical_section_number": 9}, 1) == 9
    assert section_number({"canonical_section_number": "11"}, 1) == 11
