"""Testes do respelling de pronúncia e do mapeamento alinhamento -> palavras."""
from video_gen.alignment import word_timings_from_alignment
from video_gen.pronunciation import (
    build_spoken_text,
    load_pronunciations,
    merge_pronunciations,
    parse_pronunciation_field,
)


def test_build_spoken_text_without_aliases_keeps_text_and_one_span_per_word():
    spoken, spans = build_spoken_text("Olá, mundo!", None)
    assert spoken == "Olá, mundo!"
    assert [(s.word, spoken[s.start : s.end]) for s in spans] == [
        ("Olá,", "Olá,"),
        ("mundo!", "mundo!"),
    ]


def test_build_spoken_text_replaces_case_insensitively_and_keeps_punctuation():
    spoken, spans = build_spoken_text("O WOLVERINE vazou, Wolverine!", {"wolverine": "Uólverin"})
    assert spoken == "O Uólverin vazou, Uólverin!"
    assert [s.word for s in spans] == ["O", "WOLVERINE", "vazou,", "Wolverine!"]
    assert spoken[spans[3].start : spans[3].end] == "Uólverin!"


def test_build_spoken_text_multi_word_alias_gives_each_word_its_own_span():
    spoken, spans = build_spoken_text(
        "Kingdom Hearts, chegou", {"kingdom hearts": "Kíngdom Rárts"}
    )
    assert spoken == "Kíngdom Rárts, chegou"
    assert [s.word for s in spans] == ["Kingdom", "Hearts,", "chegou"]
    assert spans[0].start == 0
    assert spans[1].end == len("Kíngdom Rárts,")
    assert spans[0].end <= spans[1].start


def test_build_spoken_text_does_not_match_inside_other_words():
    spoken, _ = build_spoken_text("Halo Halogênio", {"halo": "Rêilou"})
    assert spoken == "Rêilou Halogênio"


def test_parse_pronunciation_field():
    assert parse_pronunciation_field("Wolverine=Uólverin; Kingdom Hearts = Kíngdom Rárts;") == {
        "Wolverine": "Uólverin",
        "Kingdom Hearts": "Kíngdom Rárts",
    }
    assert parse_pronunciation_field("") == {}
    assert parse_pronunciation_field(None) == {}
    assert parse_pronunciation_field("sem sinal de igual") == {}


def test_merge_pronunciations_first_source_wins():
    merged = merge_pronunciations({"Halo": "global"}, {"halo": "por-item", "Other": "x"})
    assert merged == {"halo": "global", "other": "x"}


def test_load_pronunciations_reads_yaml(tmp_path):
    path = tmp_path / "p.yaml"
    path.write_text('"Game Pass": "Gueim Pass"\n"Empty": ""\n', encoding="utf-8")
    assert load_pronunciations(path) == {"Game Pass": "Gueim Pass"}
    assert load_pronunciations(tmp_path / "missing.yaml") == {}


def test_project_pronunciations_file_is_valid():
    aliases = load_pronunciations()
    assert aliases  # o arquivo da raiz existe e tem conteúdo
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in aliases.items())


def test_word_timings_from_alignment_uses_first_start_and_last_end_ignoring_spaces():
    spoken, spans = build_spoken_text("ab cd", None)
    chars = list(spoken)
    starts = [0.0, 0.1, 0.2, 0.3, 0.4]
    ends = [0.1, 0.2, 0.3, 0.4, 0.5]

    timings = word_timings_from_alignment(spans, chars, starts, ends)

    assert [(t.word, t.start, t.end) for t in timings] == [("ab", 0.0, 0.2), ("cd", 0.3, 0.5)]


def test_word_timings_are_monotonic_even_if_alignment_overlaps():
    spoken, spans = build_spoken_text("a b", None)
    timings = word_timings_from_alignment(spans, list(spoken), [0.0, 0.0, 0.0], [0.5, 0.5, 0.2])
    assert timings[1].start >= timings[0].end
    assert timings[1].end >= timings[1].start
