import pytest

from app.modules.ai.page_profiles import enrich_page_context, get_page_ai_profile, list_page_ai_profiles


def test_page_ai_profiles_cover_customer_utry_and_inventory_decisions() -> None:
    profiles = {item.key: item for item in list_page_ai_profiles()}

    assert profiles["customers"].primary_skill == "customer-retention"
    assert profiles["marketing-utry"].primary_skill == "utry-repurchase-diagnosis"
    assert "ask_records" in profiles["marketing-utry"].datasets
    assert "大鱼鎏金" in profiles["inventory"].diagnostic_question
    assert profiles["customers"].decision_lens["affected"] == "首购商品、沉默人群与 MINI 客群"
    assert "人数为每日累计还是跨日去重" in profiles["customers"].quality_checks


def test_all_page_ai_profiles_define_the_five_decision_layers_and_quality_checks() -> None:
    expected_layers = {"result", "cause", "affected", "action", "validation"}

    for profile in list_page_ai_profiles():
        assert set(profile.decision_lens) == expected_layers, profile.key
        assert all(profile.decision_lens.values()), profile.key
        assert len(profile.quality_checks) >= 3, profile.key


def test_page_context_keeps_filters_but_replaces_business_rules_with_trusted_profile() -> None:
    profile, context = enrich_page_context("customers", {
        "route": "/customers?tab=repeat",
        "filters": {"tab": "repeat"},
        "datasets": ["untrusted_dataset"],
        "primary_skill": "untrusted-skill",
    })

    assert profile == get_page_ai_profile("customers")
    assert context["route"] == "/customers?tab=repeat"
    assert context["filters"] == {"tab": "repeat"}
    assert context["datasets"] == list(profile.datasets)
    assert context["primary_skill"] == "customer-retention"
    assert context["decision_lens"] == profile.decision_lens
    assert context["quality_checks"] == list(profile.quality_checks)


def test_unknown_page_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown page_key"):
        enrich_page_context("missing-page", {})
