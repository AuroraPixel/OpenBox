"""The skill catalogue advertised to the model on every request.

The listing is rebuilt each step and shipped with every request, so its size is
a running cost. These tests pin the two things that kept it from being one: a
per-description cap, and a budget that degrades to names instead of growing.
"""
import pytest

from core.token import token_estimate
from permission.permission import Rule
from tool.skill_tool import (
    LISTING_BUDGET_TOKENS,
    MAX_DESCRIPTION_CHARS,
    _clip,
    _permitted,
    render_listing,
)

DESC = ("Use this skill when the user needs to work with spreadsheet files "
        "including .xlsx and .csv formats, perform data analysis, create "
        "pivot tables, or generate charts from tabular data.")


def catalogue(n, description=DESC):
    return [{"name": f"skill-{i:03d}", "description": description} for i in range(n)]


# ── clipping ──

def test_a_short_description_is_left_alone():
    assert _clip("Read spreadsheets.") == "Read spreadsheets."


def test_a_runaway_description_is_cut():
    out = _clip("x" * 40_000)
    assert len(out) <= MAX_DESCRIPTION_CHARS + 1
    assert out.endswith("…"), "the cut should be visible, not silent"


def test_whitespace_and_newlines_are_collapsed():
    # A frontmatter description written as a paragraph would otherwise ship
    # its formatting on every request.
    assert _clip("a\n\n  b\tc  ") == "a b c"


def test_clipping_survives_missing_and_empty_values():
    assert _clip("") == ""
    assert _clip(None) == ""


# ── budget ──

def test_a_small_catalogue_is_listed_in_full():
    out = render_listing(catalogue(10))
    assert out.count("<description>") == 10
    assert "<skill><name>" not in out, "nothing should be demoted at this size"


def test_a_large_catalogue_stays_within_budget_for_descriptions():
    out = render_listing(catalogue(250))
    described = out.count("<description>")
    assert described < 250, "descriptions must stop at the budget"
    # The described portion is what the budget governs; names are the floor.
    assert token_estimate(out) < 6_000


def test_no_skill_is_dropped_when_the_budget_is_hit():
    skills = catalogue(250)
    out = render_listing(skills)
    for s in skills:
        assert s["name"] in out, f"{s['name']} vanished from the listing"


def test_the_model_is_told_the_list_was_shortened():
    # Silently truncating reads as "these are all the skills there are".
    out = render_listing(catalogue(250))
    assert "budget" in out.lower()


def test_ordering_is_stable_so_the_prompt_prefix_does_not_churn():
    a = render_listing(catalogue(30))
    b = render_listing(list(reversed(catalogue(30))))
    assert a == b


def test_an_empty_catalogue_renders_without_crashing():
    out = render_listing([])
    assert "<available_skills>" in out


def test_entries_without_a_name_are_skipped():
    out = render_listing([{"name": "", "description": "x"}, {"name": "ok"}])
    assert "ok" in out
    assert out.count("<name>") == 1


def test_a_tiny_budget_still_lists_every_name():
    skills = catalogue(20)
    out = render_listing(skills, budget=1)
    assert all(s["name"] in out for s in skills)


# ── permission filtering ──

def test_denied_skills_are_not_advertised():
    # Listing a skill the agent cannot load spends tokens on every request to
    # advertise a guaranteed refusal.
    rules = [Rule(permission="skill", pattern="*", action="allow"),
             Rule(permission="skill", pattern="secret-*", action="deny")]
    out = _permitted(catalogue(3) + [{"name": "secret-ops", "description": "x"}], rules)
    assert [s["name"] for s in out] == ["skill-000", "skill-001", "skill-002"]


def test_no_rules_means_no_filtering():
    assert len(_permitted(catalogue(5), [])) == 5


def test_a_malformed_rule_does_not_hide_working_skills():
    # Agent definitions are user-editable; one bad rule must not empty the list.
    class Broken:
        permission = None
        pattern = None
        action = None
    out = _permitted(catalogue(3), [Broken()])
    assert len(out) == 3


# ── the listing must reach the model ──

@pytest.mark.asyncio
async def test_host_skills_are_listed_without_consulting_a_sandbox(monkeypatch):
    # Skills on the backend host must reach the listing on their own. Note that
    # run_loop always has a sandbox, so this is about where the two sources are
    # merged, not about a no-sandbox run — that state does not occur.
    import skill.skill as sk
    from skill.skill import SkillInfo
    from agent.tool_resolution import attach_skill_listing
    from tool.skill_tool import skill_tool

    monkeypatch.setattr(sk, "_skills",
                        {"dev-browser": SkillInfo("dev-browser", "drive a browser", "project", "b")})
    monkeypatch.setattr(sk, "_loaded", True)

    tools = await attach_skill_listing({"skill": skill_tool}, sandbox=None)
    assert "<available_skills>" in tools["skill"].description
    assert "drive a browser" in tools["skill"].description


@pytest.mark.asyncio
async def test_a_denied_skill_never_reaches_the_description(monkeypatch):
    import skill.skill as sk
    from skill.skill import SkillInfo
    from agent.tool_resolution import attach_skill_listing
    from tool.skill_tool import skill_tool

    monkeypatch.setattr(sk, "_skills", {
        "ok": SkillInfo("ok", "fine", "project", "b"),
        "secret-ops": SkillInfo("secret-ops", "classified", "project", "b"),
    })
    monkeypatch.setattr(sk, "_loaded", True)

    rules = [Rule(permission="skill", pattern="secret-*", action="deny")]
    tools = await attach_skill_listing({"skill": skill_tool}, sandbox=None, ruleset=rules)
    assert "classified" not in tools["skill"].description
    assert "secret-ops" not in tools["skill"].description


@pytest.mark.asyncio
async def test_no_skill_tool_means_nothing_to_do(monkeypatch):
    from agent.tool_resolution import attach_skill_listing
    tools = await attach_skill_listing({"bash": object()}, sandbox=None)
    assert list(tools) == ["bash"]
