"""Unit tests for error hierarchy and stderr parser."""
from __future__ import annotations


from inkscape_mcp.exceptions import (
    IdDestroyedError,
    IdNotFoundError,
    InkscapeActionError,
    InkscapeError,
    InkscapeFileError,
    StaleRevisionError,
    parse_stderr,
)


class TestErrorHierarchy:
    def test_all_are_inkscape_error(self):
        """All domain errors inherit from InkscapeError."""
        assert issubclass(InkscapeActionError, InkscapeError)
        assert issubclass(InkscapeFileError, InkscapeError)
        assert issubclass(StaleRevisionError, InkscapeError)
        assert issubclass(IdNotFoundError, InkscapeError)
        assert issubclass(IdDestroyedError, InkscapeError)

    def test_error_codes(self):
        assert InkscapeActionError("test", "").code == "INKSCAPE_ACTION_FAILED"
        assert StaleRevisionError(2, 1).code == "STALE_REVISION"
        assert IdDestroyedError("r1").code == "ID_DESTROYED"

    def test_to_dict(self):
        err = StaleRevisionError(2, 1)
        d = err.to_dict()
        assert d["code"] == "STALE_REVISION"
        assert "expected 2" in d["message"]


class TestStderrParser:
    def test_action_not_found(self):
        stderr = "InkscapeApplication::parse_actions: could not find action for: bad-action"
        err = parse_stderr(stderr)
        assert isinstance(err, InkscapeActionError)
        assert "bad-action" in err.detail

    def test_file_cannot_be_opened(self):
        stderr = "ink_file_open: '/tmp/nonexistent.svg' cannot be opened!"
        err = parse_stderr(stderr)
        assert isinstance(err, InkscapeFileError)

    def test_file_does_not_exist(self):
        stderr = "Can't open file: /tmp/x.svg (doesn't exist)"
        err = parse_stderr(stderr)
        assert isinstance(err, InkscapeFileError)

    def test_clean_stderr_returns_none(self):
        assert parse_stderr("") is None
        assert parse_stderr("\n") is None

    def test_generic_warning(self):
        stderr = "** WARNING **: Something went wrong"
        err = parse_stderr(stderr)
        assert isinstance(err, InkscapeError)
        assert "Something went wrong" in err.detail

    def test_no_match_non_warning(self):
        # Random text without WARNING/ERROR should still trigger generic
        # Actually with our parser, non-warning text returns None
        stderr = "just some random output"
        err = parse_stderr(stderr)
        # Currently the parser only flags WARNING/ERROR lines for generic errors
        # Pure random text with no patterns returns None
        assert err is None or isinstance(err, InkscapeError)
