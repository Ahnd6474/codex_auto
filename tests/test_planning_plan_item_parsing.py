from jakal_flow.planning import extract_plan_items, validate_mid_term_subset


def test_extract_plan_items_parses_heading_style_plan_ids() -> None:
    plan_text = """# Project Plan

## Focus Areas
## PL1 - Improve git recovery resilience with stricter rollback guards
## PL2 - Increase automated verification around recovery state transitions
"""

    items = extract_plan_items(plan_text)

    assert [item.item_id for item in items] == ["PL1", "PL2"]


def test_validate_mid_term_subset_accepts_heading_style_plan_ids() -> None:
    plan_text = """# Project Plan

## Focus Areas
## PL1 - Improve git recovery resilience with stricter rollback guards
"""
    mid_term_text = "- [ ] MT1 -> PL1: Improve git recovery resilience with stricter rollback guards\n"

    valid, violations = validate_mid_term_subset(mid_term_text, plan_text)

    assert valid is True
    assert violations == []
