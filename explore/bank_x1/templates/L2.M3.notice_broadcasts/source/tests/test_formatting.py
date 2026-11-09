from broadcasts.formatting import MAX_BODY_CHARS, subject_line, truncate_body


def test_short_body_is_unchanged():
    assert truncate_body("Portal  back\nonline.") == "Portal back online."


def test_long_body_is_cut_on_word_boundary():
    text = truncate_body("alpha " * 200)
    assert len(text) <= MAX_BODY_CHARS
    assert text.endswith("alpha...")


def test_subject_prefix():
    assert subject_line("incident", " API errors ") == "[Service incident] API errors"
    assert subject_line("other", "x") == "[Notice] x"
