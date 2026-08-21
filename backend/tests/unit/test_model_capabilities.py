"""Context-window and vision resolution from a model id.

The heuristics are ordered-substring matching, which has one specific trap: a
narrower id contains a wider one. `gpt-5.4-mini` contains `gpt-5.4`, so a rule
list in the wrong order silently hands a 400k model a 1M budget — compaction
then never fires and every long run dies on a provider error instead.
"""
import pytest

from agent.compaction import _heuristic_context_limit
from agent.vision import supports_vision


@pytest.mark.parametrize(
    "model_id,expected",
    [
        # GPT-5 defaults to the smaller window the common gateways actually
        # serve, not the larger one OpenAI quotes direct.
        ("openai/gpt-5.4-mini", 256_000),
        ("openai/gpt-5.4", 256_000),
        ("openai/gpt-5.3-codex", 256_000),
        ("openai/gpt-5.6-luna", 256_000),
        # Claude: 4.6 and up carry the 1M window, the 4.5-era Haiku does not.
        ("anthropic/claude-opus-5", 1_000_000),
        ("anthropic/claude-sonnet-4-6", 1_000_000),
        ("anthropic/claude-haiku-4-5", 200_000),
        ("anthropic/claude-3-5-sonnet", 200_000),
        # DeepSeek V4 raised the line to 1M; the legacy ids stayed at 128k.
        ("deepseek/deepseek-v4-pro", 1_000_000),
        ("deepseek/deepseek-chat", 128_000),
        ("deepseek/deepseek-reasoner", 128_000),
        ("google/gemini-3.1-pro", 1_000_000),
        ("openai/gpt-4o", 128_000),
    ],
)
def test_heuristic_context_limit(model_id: str, expected: int) -> None:
    assert _heuristic_context_limit(model_id) == expected


def test_unknown_model_gets_the_conservative_default() -> None:
    """Guessing high is the dangerous direction: no compaction, then a 400."""
    assert _heuristic_context_limit("mystery/llama-9") == 200_000


@pytest.mark.parametrize(
    "model_id,expected",
    [
        # DeepSeek ships vision as separate ids, so the base models are text-only.
        ("deepseek/deepseek-v4-flash", False),
        ("deepseek/deepseek-chat", False),
        ("deepseek/deepseek-v4-flash-vision-exp", True),
        ("qwen/qwen3-vl-plus", True),
        ("openai/gpt-5.6-luna", True),
        ("anthropic/claude-opus-5", True),
    ],
)
def test_supports_vision(model_id: str, expected: bool) -> None:
    assert supports_vision(model_id) is expected


def test_unknown_model_is_assumed_multimodal() -> None:
    """Dropping a screenshot silently is worse than a provider error: the model
    then answers confidently about a screen it was never shown."""
    assert supports_vision("mystery/llama-9") is True


@pytest.mark.asyncio
async def test_text_only_model_gets_a_note_instead_of_images() -> None:
    """A conversation outlives the model it started on.

    Screenshots taken on a vision model keep arriving at whatever model is
    selected now; sending them anyway buys a gateway 400 that kills the turn.
    """
    from agent.loop import resolve_images

    messages = [{
        "role": "user",
        "content": "what is on screen?",
        "_images": [{"asset_id": "a1", "key": "k1", "mime": "image/png"}],
    }]
    out = await resolve_images(messages, "openai/deepseek-v4-flash")

    assert "_images" not in out[0], "the reference must not reach a text-only model"
    assert "cannot read images" in out[0]["content"]
    assert "what is on screen?" in out[0]["content"], "the question itself must survive"


@pytest.mark.asyncio
async def test_vision_model_keeps_its_image_references() -> None:
    """The gate must not fire on a model that can actually see."""
    from agent import loop

    messages = [{
        "role": "user",
        "content": "what is on screen?",
        "_images": [{"asset_id": "a2", "key": "k2", "mime": "image/png"}],
    }]
    # Pre-seed the cache so the test never reaches OSS.
    loop._IMAGE_CACHE["a2"] = "data:image/png;base64,AAA"
    out = await loop.resolve_images(messages, "openai/gpt-5.6-luna")

    assert out[0]["_images"] == ["data:image/png;base64,AAA"]
    assert "cannot read images" not in out[0]["content"]
