"""Which model a run actually uses.

A session stores the model it was started with, and that value outlives the
configuration: swap the provider gateway and every old conversation still
carries a name the new gateway has never heard of. The request then fails deep
inside the provider — as an opaque "no channel available for model X" that the
retry layer dutifully attempts five times before giving up.

So a stored name is a *preference*, not an instruction. It is honoured when the
deployment still offers it and quietly replaced by the default when it does
not, which is what lets an old conversation continue after a provider change
instead of erroring forever.
"""
from core.log import create_logger

log = create_logger("agent.model")


def configured_models(config) -> list[str]:
    """Model ids this deployment offers, default included."""
    ids = [m.id for m in (config.models or []) if m.id]
    if config.model and config.model not in ids:
        ids.insert(0, config.model)
    return ids


def is_available(model_id: str, config) -> bool:
    """Whether the deployment still offers this model.

    An empty `models` list means the deployment never enumerated them, so
    nothing can be ruled out — only the explicitly configured case can say a
    model is gone.
    """
    if not model_id:
        return False
    if not config.models:
        return True
    return model_id in configured_models(config)


def resolve(requested: str | None, config, *, context: str = "") -> tuple[str, str | None]:
    """The model to run with, plus a note when it is not the one requested.

    Returns (model_id, replaced_from). `replaced_from` is the unavailable name
    that was dropped, so callers can tell the user their old conversation
    switched models rather than silently changing behaviour underfoot.
    """
    fallback = config.model or "anthropic/claude-sonnet-4-20250514"
    if not requested:
        return fallback, None
    if is_available(requested, config):
        return requested, None

    log.info(
        "model %r is not configured%s; falling back to %r",
        requested, f" ({context})" if context else "", fallback,
    )
    return fallback, requested
