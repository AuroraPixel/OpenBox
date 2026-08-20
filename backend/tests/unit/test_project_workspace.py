"""Projects: the naming rules that become directory names, and the fallbacks.

A slug is written into a shell command as a path segment, so the validation
here is the only thing between a project name and an arbitrary path.
"""
import pytest

from project.workspace import (
    DEFAULT_SLUG,
    ProjectError,
    project_directory,
    slugify,
    validate_slug,
)


# ── slugify ──

@pytest.mark.parametrize("name,expected", [
    ("My Project", "my-project"),
    ("  Padded  ", "padded"),
    ("UPPER", "upper"),
    ("with_underscores", "with-underscores"),
    ("multiple   spaces", "multiple-spaces"),
    ("dots.are.fine", "dots.are.fine"),
    ("trailing---", "trailing"),
    ("a//b\\c", "abc"),
])
def test_slugify_produces_a_directory_name(name, expected):
    assert slugify(name) == expected


def test_slugify_drops_characters_that_cannot_be_a_path_segment():
    assert "/" not in slugify("a/b")
    assert ".." not in slugify("../../etc")
    assert " " not in slugify("a b")


def test_a_name_with_no_ascii_slugifies_to_nothing():
    # Callers fall back to a generated slug rather than writing an empty path.
    assert slugify("中文项目") == ""
    assert slugify("🎉") == ""


def test_slugify_is_length_bounded():
    assert len(slugify("x" * 500)) <= 64


# ── validate_slug ──

def test_a_normal_slug_passes():
    assert validate_slug("my-project") == "my-project"
    assert validate_slug("proj.2") == "proj.2"


@pytest.mark.parametrize("slug", ["", ".", "..", ".openbox", "sessions", "skills", "trash"])
def test_reserved_names_are_refused(slug):
    with pytest.raises(ProjectError):
        validate_slug(slug)


@pytest.mark.parametrize("slug", [
    "../escape",       # path traversal
    "/absolute",
    "with space",
    "UPPER",           # slugify lowercases; a raw slug must already be lower
    "-leading",        # must start alphanumeric
    ".hidden",
    "semi;colon",
    "x" * 65,          # too long for a comfortable path segment
])
def test_unsafe_slugs_are_refused(slug):
    with pytest.raises(ProjectError):
        validate_slug(slug)


# ── directory ──

def test_directory_is_under_the_workspace_root():
    assert project_directory("demo") == "/workspace/demo"


def test_the_default_project_has_a_directory_like_any_other():
    assert project_directory(DEFAULT_SLUG) == "/workspace/default"
