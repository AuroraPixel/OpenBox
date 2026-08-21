"""Which models can read an image.

This exists because the failure mode is expensive and unhelpful: a screenshot
reaches a text-only model, the gateway answers `This model does not support
image`, and the whole turn is lost — after the tool ran, after the screenshot
was captured and uploaded. The user sees a red box naming neither the image nor
the model.

Attachments are also durable. A conversation started on a vision model keeps
its screenshots forever, so the question is not asked once at upload time but
again on every later turn, including turns the user switched models for. That
makes this the same defect class as model names and tool-call ids: something
persisted under one provider, replayed to another.

Config wins over the heuristic here, because only the gateway operator knows
which variant they actually route to.
"""
from core.log import create_logger

log = create_logger("agent.vision")

#: Families that are text-only regardless of how modern they are. DeepSeek
#: ships vision as separate `-vision-*` models rather than as a capability of
#: the base one, so the base ids must be excluded by name.
_TEXT_ONLY_FAMILIES = ("deepseek", "qwq", "o1-mini")

#: Substrings that re-enable vision inside an otherwise text-only family.
_VISION_MARKERS = ("vision", "-vl", "multimodal")


def supports_vision(model_id: str) -> bool:
    """Whether `model_id` accepts image input.

    Unknown models are assumed to be multimodal. That is the honest default in
    2026 and it fails loudly (a provider error naming the problem) rather than
    quietly — silently dropping a screenshot would leave the model answering
    confidently about a screen it never saw, which is strictly worse.
    """
    # 1. Explicit config, which the gateway operator controls.
    try:
        from core.config import get_config
        for m in get_config().models:
            if m.id == model_id and m.vision is not None:
                return m.vision
    except Exception:
        pass

    # 2. Family heuristic.
    lowered = model_id.lower()
    if any(marker in lowered for marker in _VISION_MARKERS):
        return True
    if any(family in lowered for family in _TEXT_ONLY_FAMILIES):
        return False
    return True


def describe_dropped(count: int) -> str:
    """The note that replaces images a text-only model cannot be shown.

    Written for the model, not the user: it has to understand that something
    was withheld from it, or it will answer about the picture anyway.
    """
    noun = "image" if count == 1 else f"{count} images"
    return (
        f"[{noun} omitted: the current model cannot read images. "
        f"Do not guess at the content — say that this model cannot see it, and "
        f"offer to continue on a vision-capable model.]"
    )
