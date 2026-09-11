"""Testes do filtro de palavras-chave."""
from dedupe.keyword_filter import find_matched_keywords, is_relevant


def test_finds_keyword_in_title():
    assert is_relevant("Big Sequel Leaked Ahead of Reveal") is True


def test_finds_keyword_case_insensitive():
    matched = find_matched_keywords("STUDIO delayed THE GAME again")
    assert "delayed" in matched
    assert "delay" not in matched  # forma "delay" isolada não está presente


def test_no_keyword_returns_not_relevant():
    assert is_relevant("A quiet day in the gaming industry") is False


def test_searches_summary_too():
    matched = find_matched_keywords(
        title="Nothing special here",
        summary="But sources say this was an exclusive first look.",
    )
    assert "exclusive" in matched


def test_does_not_match_substring_inside_other_word():
    # "release" sozinho não deve casar com "release date" nem gerar falso positivo
    matched = find_matched_keywords("The prerelease build was fine")
    assert matched == []


def test_matches_multi_word_keyword():
    matched = find_matched_keywords("New release date confirmed for the sequel")
    assert "release date" in matched
    assert "confirmed" in matched


def test_custom_keyword_list():
    matched = find_matched_keywords(
        "Nintendo Direct scheduled for next week", keywords=["nintendo direct"]
    )
    assert matched == ["nintendo direct"]


def test_returns_empty_list_when_no_match_with_custom_keywords():
    assert find_matched_keywords("Random news", keywords=["nintendo direct"]) == []
