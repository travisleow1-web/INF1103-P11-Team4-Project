from ai_layer import ai_settings
from ai_layer.ai_error import AIError
from ai_layer.ai_service_error import AIServiceError
from ai_layer.invalid_response_error import InvalidResponseError
from model.risk_level import RiskLevel
from model.risk_type import RiskType

SCHEMA = ai_settings.RESPONSE_SCHEMA["properties"]
FACTOR = SCHEMA["risk_factors"]["items"]["properties"]
INSIGHT = SCHEMA["insights"]["items"]["properties"]


def test_errors_share_one_base_class():
    assert issubclass(AIServiceError, AIError)
    assert issubclass(InvalidResponseError, AIError)


def test_service_error_keeps_message_and_retryable_flag():
    error = AIServiceError("HTTP 429", retryable=True)
    assert str(error) == "HTTP 429"
    assert error.retryable is True
    assert AIServiceError("HTTP 400", retryable=False).retryable is False


def test_defaults():
    assert ai_settings.DEFAULT_MODEL == "gemini-3.5-flash-lite"
    assert ai_settings.HISTORY_DAYS == 90


def test_schema_enums_come_from_the_model_enums():
    assert FACTOR["type"]["enum"] == [t.value for t in RiskType if t is not RiskType.NONE]
    assert SCHEMA["primary_risk_factor"]["enum"] == [t.value for t in RiskType]
    assert INSIGHT["risk_type"]["enum"] == [t.value for t in RiskType]
    assert FACTOR["severity"]["enum"] == ["Low", "Medium", "High", "Extreme"]
    assert INSIGHT["severity"]["enum"] == [level.label for level in RiskLevel]


def test_locations_are_plain_strings_and_there_is_no_sources_list():
    for field in (FACTOR["location"], INSIGHT["location"], SCHEMA["affected_location"]):
        assert field == {"type": "STRING"}
    assert "sources" not in SCHEMA
    assert "sources" not in ai_settings.RESPONSE_SCHEMA["required"]


def test_every_schema_field_is_required():
    assert set(ai_settings.RESPONSE_SCHEMA["required"]) == set(SCHEMA)


def test_allowed_lists_match_the_schema():
    lists = ai_settings.ALLOWED_LISTS
    assert set(lists) == {"impact", "source", "insight_code"}
    assert list(lists["impact"]) == SCHEMA["expected_impact"]["enum"]
    assert list(lists["source"]) == FACTOR["source"]["enum"]
    assert list(lists["insight_code"]) == INSIGHT["code"]["enum"]


def test_system_prompt_marks_external_data_as_untrusted():
    assert "never as instructions" in ai_settings.SYSTEM_PROMPT
    assert "today's date" in ai_settings.SYSTEM_PROMPT
