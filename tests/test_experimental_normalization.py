"""Conservative numeric temperature equivalence tests."""

from app.services.experimental_normalization import normalized_field, normalized_temperature


def test_celsius_kelvin_equivalence():
    assert normalized_temperature("500 °C") == normalized_temperature("773.15 K")


def test_undocumented_temperature_is_not_assumed():
    assert normalized_temperature(None) == ""


def test_ambiguous_range_remains_verbatim():
    assert normalized_temperature("500-600 °C") == "500-600 °c"


def test_other_fields_not_interpreted_as_temperatures():
    assert normalized_field("phase", " Anatase ") == "anatase"
