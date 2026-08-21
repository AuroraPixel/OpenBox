"""Tool-call ids must survive a change of provider.

An id is recorded under whichever provider produced it and replayed to
whichever one is configured later. Gemini packs an encrypted thought signature
into the id, and the OpenAI Responses API is strict about what it will take
back. Three separate rules have bitten so far, each surfacing as a different
opaque 400 that named neither the value nor the provider switch:

1. length — over 64 characters is "string too long"
2. character set — base64 brings `+` and `/`
3. **a trailing separator** — an id ending in `_` is rejected, and the API
   reports it as "Expected an ID that contains letters, numbers, underscores,
   or dashes, but this value contained additional characters", which describes
   a violation the value does not have

Rule 3 was established by probing the API directly:

    fc_abcDEF     accepted        fc_abcDEF_    rejected
    fc_abcDEF-    accepted        fc_abcDEF__   rejected
    fc__abcDEF    accepted        fc_           rejected
    fc_abcDEF9    accepted

Because the rules keep arriving one at a time, the implementation validates a
positive pattern and replaces anything that fails, rather than enumerating
known-bad shapes. These tests import that implementation. They used to carry a
*copy* of it, which is how rule 3 shipped green: the copy stayed valid while
the real function drifted.
"""
import re

from agent.llm import _FC_ID_OK, build_responses_input, ensure_fc_id
from agent.processor import MAX_CALL_ID, sanitize_call_id

SAFE = re.compile(r"[A-Za-z0-9_-]+")

#: A real one from the database: base64, so it carries `+` and `/` too.
GEMINI_ID = "call_309329__thought__AY89a1+THtr7/tUaa9DktKdE5" + "x" * 6000

#: Verbatim from the user-facing failure. 62 characters, letters/digits/
#: underscores only — it passes a length check and a character-set check, and
#: is still rejected, because it ends on `_`.
TRAILING_UNDERSCORE_ID = "call_2126559__thought__AY89a1_C0Q1n8oaLIeeRMcuL_qIYGuV_fs__JuxL_"


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
    """The API constrains ids more than one way. Fixing only the length left
    `+` and `/` behind, and the same turn failed again with a new message."""
    assert SAFE.fullmatch(ensure_fc_id("call_abc+def/ghi"))


def test_an_id_ending_in_an_underscore_is_replaced():
    """Rule 3. Short enough and clean enough to pass the first two checks."""
    out = ensure_fc_id(TRAILING_UNDERSCORE_ID)
    assert not out.endswith("_")
    assert _FC_ID_OK.fullmatch(out)


def test_a_clean_thought_signature_id_survives_intact():
    """The point is not to hash everything. An id that the API accepts should
    reach it unchanged, so logs and traces stay readable."""
    clean = "call_5019__thought__AY89a19_432KM9rvUOiEKenAAwpH1DTsPh9HHgyZrPkw"
    assert ensure_fc_id(clean) == "fc_5019__thought__AY89a19_432KM9rvUOiEKenAAwpH1DTsPh9HHgyZrPkw"


def test_every_output_satisfies_the_pattern():
    """The whole contract in one line: whatever goes in, what comes out is
    something the API will take."""
    for raw in (
        GEMINI_ID,
        TRAILING_UNDERSCORE_ID,
        "call_abc123",
        "fc_abcDEF_",
        "fc_",
        "",
        "call_a+b/c=",
        "_" * 80,
        "call_" + "-" * 70,
    ):
        assert _FC_ID_OK.fullmatch(ensure_fc_id(raw)), f"{raw[:40]!r} produced an illegal id"


def test_write_side_produces_a_legal_id():
    out = sanitize_call_id(GEMINI_ID)
    assert len(out) <= MAX_CALL_ID
    assert SAFE.fullmatch(out), "illegal characters must not reach the database"


def test_write_side_never_ends_on_a_separator():
    """This function is the source of the separators, not just a victim of
    them: substitution turns `/` into `_`, and the clip can land on one."""
    for raw in ("abc/def+", "a" * 63 + "/rest", "call_x_", "call_y-"):
        assert not sanitize_call_id(raw).endswith(("_", "-")), raw


def test_write_side_never_returns_empty():
    """An empty id pairs a call with the wrong result, or with none."""
    assert sanitize_call_id("____") == "call"
    assert sanitize_call_id("") == "call"
    assert sanitize_call_id("+++") == "call"


def test_write_side_leaves_a_clean_id_alone():
    assert sanitize_call_id("call_abc-123_XY") == "call_abc-123_XY"


def test_write_side_is_deterministic():
    assert sanitize_call_id(GEMINI_ID) == sanitize_call_id(GEMINI_ID)


def test_write_and_read_sides_compose():
    """The real path: a provider id is normalised on the way into the database,
    then normalised again on the way out to a different provider."""
    for raw in (GEMINI_ID, TRAILING_UNDERSCORE_ID, "call_a+b/c=", "x" * 200):
        assert _FC_ID_OK.fullmatch(ensure_fc_id(sanitize_call_id(raw)))


def test_narration_survives_a_tool_call_turn():
    """A turn that spoke and then called a tool must replay both.

    The message carries `content` and `tool_calls` together. Emitting only the
    calls drops the model's stated reasoning from the replayed context — and
    nothing rejects a shorter history, so the loss is silent.
    """
    built = build_responses_input([{
        "role": "assistant",
        "content": "Let me check the file first.",
        "tool_calls": [{
            "id": "call_abc123",
            "function": {"name": "read", "arguments": '{"path":"x"}'},
        }],
    }])

    assert built[0] == {"role": "assistant", "content": "Let me check the file first."}
    assert built[1]["type"] == "function_call"
    assert built[1]["id"] == "fc_abc123"


def test_a_silent_tool_call_turn_adds_no_empty_message():
    """An empty or whitespace `content` must not become a blank assistant item."""
    for content in ("", "   ", None):
        built = build_responses_input([{
            "role": "assistant",
            "content": content,
            "tool_calls": [{"id": "call_x", "function": {"name": "read", "arguments": "{}"}}],
        }])
        assert len(built) == 1, f"content={content!r} produced {built}"
        assert built[0]["type"] == "function_call"


def test_the_builder_normalises_ids_on_both_sides_of_a_pair():
    """The call and its result must still address each other after rewriting."""
    built = build_responses_input([
        {"role": "assistant", "tool_calls": [
            {"id": TRAILING_UNDERSCORE_ID, "function": {"name": "read", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": TRAILING_UNDERSCORE_ID, "content": "ok"},
    ])
    call, result = built[0], built[1]
    assert call["call_id"] == result["call_id"], "the pair came apart"
    assert _FC_ID_OK.fullmatch(call["call_id"])
