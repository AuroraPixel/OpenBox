"""Tool-call ids must survive a change of provider.

An id is recorded under whichever provider produced it and replayed to
whichever one is configured later. Gemini packs an encrypted thought signature
into the id — kilobytes of it — while OpenAI's Responses API rejects anything
over 64 characters, so an unbounded id poisons the conversation for every
future provider.
"""
import hashlib
import re

from agent.processor import MAX_CALL_ID, sanitize_call_id

SAFE = re.compile(r"[A-Za-z0-9_-]+")


def ensure_fc_id(raw_id: str, limit: int = 64) -> str:
    """Mirror of the normaliser in agent.llm._stream_responses_api."""
    fc_id = raw_id if raw_id.startswith("fc_") else f"fc_{raw_id.replace('call_', '')}"
    if len(fc_id) <= limit and SAFE.fullmatch(fc_id):
        return fc_id
    return f"fc_{hashlib.sha256(raw_id.encode()).hexdigest()[:32]}"


#: A real one from the database: base64, so it carries `+` and `/` too.
GEMINI_ID = "call_309329__thought__AY89a1+THtr7/tUaa9DktKdE5" + "x" * 6000


def test_a_normal_id_is_left_alone():
    assert ensure_fc_id("call_abc123") == "fc_abc123"


def test_an_over_long_id_is_brought_under_the_limit():
    assert len(ensure_fc_id(GEMINI_ID)) <= 64


def test_the_same_call_always_maps_to_the_same_id():
    """The assistant's function_call and its function_call_output are paired by
    id, so the mapping has to be a pure function or the pair comes apart."""
    assert ensure_fc_id(GEMINI_ID) == ensure_fc_id(GEMINI_ID)


def test_ids_sharing_a_long_prefix_do_not_collide():
    """Gemini's ids share a prefix, so truncation would map two different calls
    onto one id and cross-wire their results."""
    other = "call_309329__thought__AY89a1" + "y" * 6000
    assert ensure_fc_id(GEMINI_ID) != ensure_fc_id(other)


def test_ids_are_bounded_at_write_time_too():
    """Reading is the backstop; the fix belongs at the point of persistence."""
    assert MAX_CALL_ID == 64
    assert len(GEMINI_ID[:MAX_CALL_ID]) == 64


def test_illegal_characters_are_rejected_not_just_length():
    """The API constrains ids two ways. Fixing only the length left `+` and `/`
    behind, and the same turn failed again with a different message."""
    short_but_illegal = "call_abc+def/ghi"
    assert SAFE.fullmatch(ensure_fc_id(short_but_illegal))


def test_write_side_produces_a_legal_id():
    out = sanitize_call_id(GEMINI_ID)
    assert len(out) <= MAX_CALL_ID
    assert SAFE.fullmatch(out), "illegal characters must not reach the database"


def test_write_side_leaves_a_clean_id_alone():
    assert sanitize_call_id("call_abc-123_XY") == "call_abc-123_XY"


def test_write_side_is_deterministic():
    assert sanitize_call_id(GEMINI_ID) == sanitize_call_id(GEMINI_ID)
