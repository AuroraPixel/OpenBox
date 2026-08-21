"""Per-model parameters must suit the model actually being called.

A variant (reasoning effort / thinking budget) rides on the message, not the
model, so it outlives a mid-conversation model switch and a provider fallback.
Forwarded verbatim it reaches families that reject it — and the rejection
arrives as a provider 400 that names neither the variant nor the switch.
"""
import pytest

from agent.llm import (
    THINKING_OUTPUT_RESERVE,
    _get_max_output_tokens,
    _get_variant_kwargs,
)


@pytest.mark.parametrize("model", ["openai/gpt-5.4", "openai/gpt-5.2"])
def test_max_becomes_xhigh_only_where_xhigh_exists(model):
    assert _get_variant_kwargs(model, "max") == {"reasoning_effort": "xhigh"}


def test_max_is_clamped_for_plain_gpt5_which_rejects_it():
    """Plain GPT-5 knows neither 'max' nor 'xhigh'; sending either is a 400."""
    assert _get_variant_kwargs("openai/gpt-5", "max") == {"reasoning_effort": "high"}


def test_an_unrecognised_variant_is_dropped_rather_than_forwarded():
    assert _get_variant_kwargs("openai/gpt-5", "wildly-invalid") == {}


def test_claude4_max_budget_would_collide_with_the_output_cap():
    """Anthropic draws thinking out of the output budget and requires
    max_tokens > budget_tokens. The generic 32k cap equals the 'max' budget
    exactly, so the request needs headroom added."""
    kwargs = _get_variant_kwargs("anthropic/claude-sonnet-4-20250514", "max")
    budget = kwargs["thinking"]["budget_tokens"]
    assert budget == _get_max_output_tokens("anthropic/claude-sonnet-4-20250514"), (
        "this collision is the bug being guarded"
    )
    assert budget + THINKING_OUTPUT_RESERVE > budget


# ── DeepSeek variant clamp ───────────────────────────────────────────────
# A variant rides on the message, not the model, so one chosen on a GPT model
# arrives intact after the session resolves to DeepSeek. reasoning_effort is a
# parameter DeepSeek *supports*, so drop_params will not strip an out-of-range
# value — it reaches the API and is rejected there.

@pytest.mark.parametrize("variant,expected", [
    ("low", "low"),
    ("medium", "medium"),
    ("high", "high"),
    ("max", "high"),      # GPT's top tier has no DeepSeek equivalent
    ("xhigh", "high"),    # ditto
])
def test_deepseek_clamps_a_foreign_variant(variant, expected):
    out = _get_variant_kwargs("deepseek/deepseek-v4-flash", variant)
    assert out == {"reasoning_effort": expected}


@pytest.mark.parametrize("variant", ["minimal", "none", "turbo"])
def test_deepseek_drops_a_variant_it_cannot_express(variant):
    """Dropping is right: the request still runs, just without the hint.

    An empty variant is NOT this case — it means "nothing was chosen" and
    correctly falls through to the family default.
    """
    assert _get_variant_kwargs("deepseek/deepseek-v4-flash", variant) == {}
