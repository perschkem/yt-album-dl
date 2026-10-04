from ytdl.errors import clean_error


def test_clean_error_strips_ytdlp_prefix_and_whitespace():
    assert clean_error(RuntimeError("ERROR: [youtube] x: Private video \n")) == "[youtube] x: Private video"
    assert clean_error("HTTP Error 503") == "HTTP Error 503"
    assert clean_error(ValueError("Fehler: ERROR: bleibt")) == "Fehler: ERROR: bleibt"  # nur am Anfang
