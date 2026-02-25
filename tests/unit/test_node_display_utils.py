from shared.utils.node_display import (
    country_code_from_region,
    flag_emoji_from_country_code,
    format_node_display_name,
)


def test_country_code_from_region_simple_iso():
    assert country_code_from_region("fi") == "FI"


def test_country_code_from_region_alias():
    assert country_code_from_region("uk") == "GB"


def test_country_code_from_region_composite_token():
    assert country_code_from_region("eu-fi-01") == "FI"


def test_flag_emoji_from_country_code():
    assert flag_emoji_from_country_code("fi") == "🇫🇮"


def test_format_node_display_name_with_mapping():
    value = format_node_display_name(node_name="be-fi-1", region="fi")
    assert value == "🇫🇮 Finland | be-fi-1"


def test_format_node_display_name_unknown_region_falls_back_to_node_name():
    value = format_node_display_name(node_name="backend-1", region="unknown")
    assert value == "backend-1"
