"""Testes do checklist de SEO (funções puras, sem banco nem rede)."""
from webapp.seo import (
    caption_lead,
    check_seo,
    extract_hashtags,
    first_word,
    has_br_hashtag,
    hashtags_with_accent,
    hashtags_with_space,
    seo_score,
)


def make_item(**overrides):
    item = {
        "script_description": "GTA 6 vazou a data! Olha isso. #fyp #gaming #games #gta6",
        "script_hook": "O trailer de GTA 6 quebrou o mercado de console!",
        "script_cta": "Comenta aí o que cê achou!",
        "game_name": "Grand Theft Auto VI",
    }
    item.update(overrides)
    return item


def check_by_prefix(checks, prefix):
    return next(c for c in checks if c.label.startswith(prefix))


# --- helpers ---------------------------------------------------------------


def test_extract_hashtags_lowercases_and_drops_hash():
    assert extract_hashtags("Texto #FYP #GTA6 fim") == ["fyp", "gta6"]
    assert extract_hashtags("") == []


def test_caption_lead_is_text_before_first_hashtag():
    assert caption_lead("Vazou a data de GTA 6! #fyp #games") == "Vazou a data de GTA 6!"
    assert caption_lead("#soHashtag") == ""


def test_first_word_normalizes():
    assert first_word("GENTE, olha isso") == "gente"
    assert first_word("") == ""


# --- regras ----------------------------------------------------------------


def test_all_checks_pass_for_a_good_item():
    checks = check_seo(make_item(), recent_hooks=["Vazou o final de Wolverine!"])
    assert all(c.ok for c in checks)
    assert seo_score(checks) == (len(checks), len(checks))


def test_missing_description_fails():
    checks = check_seo(make_item(script_description=""))
    assert not check_by_prefix(checks, "Legenda").ok


def test_long_lead_fails():
    long_lead = "a" * 151
    checks = check_seo(make_item(script_description=f"{long_lead} #fyp #games #gaming #gta6"))
    assert not check_by_prefix(checks, "Primeira frase").ok


def test_hashtag_count_out_of_range_fails():
    few = check_seo(make_item(script_description="Texto #fyp #games"))
    assert not check_by_prefix(few, "4 a 6 hashtags").ok

    many = check_seo(
        make_item(script_description="Texto #a #b #c #games #d #e #f")
    )
    assert not check_by_prefix(many, "4 a 6 hashtags").ok


def test_english_only_hashtags_fail_br_check():
    checks = check_seo(make_item(script_description="Texto #fyp #gaming #gamertok #gta6"))
    assert not check_by_prefix(checks, "Tem hashtag em português").ok


def test_has_br_hashtag_accepts_any_of_the_terms():
    assert has_br_hashtag("#fyp #jogos") is True
    assert has_br_hashtag("#fyp #noticiasdegames") is True
    assert has_br_hashtag("#fyp #gaming") is False


def test_hashtag_with_space_is_detected():
    description = "RE4 tem falas cortadas #gaming #games #re4 #leon kennedy"
    assert hashtags_with_space(description) == ["#leon kennedy"]
    checks = check_seo(make_item(script_description=description))
    espaco = check_by_prefix(checks, "Nenhuma hashtag com espaço")
    assert not espaco.ok
    assert "#leon kennedy" in espaco.hint


def test_hashtag_with_accent_is_detected():
    description = "Notícia quente #fyp #games #notícias #gta6"
    assert hashtags_with_accent(description) == ["notícias"]
    assert not check_by_prefix(
        check_seo(make_item(script_description=description)), "Nenhuma hashtag com acento"
    ).ok


def test_text_with_accent_outside_hashtag_is_fine():
    description = "Notícia quente de vazamento! #fyp #games #gaming #gta6"
    assert hashtags_with_accent(description) == []
    assert hashtags_with_space(description) == []


def test_missing_game_name_fails():
    assert not check_by_prefix(check_seo(make_item(game_name="")), "Nome do jogo").ok


def test_long_hook_fails():
    hook = " ".join(["palavra"] * 13)
    assert not check_by_prefix(check_seo(make_item(script_hook=hook)), "Hook com até").ok


def test_repeated_opening_fails_and_names_the_word():
    checks = check_seo(
        make_item(script_hook="GENTE, o Switch 2 foi desmontado!"),
        recent_hooks=["GENTE, o Forza continua de pé!", "Vazou o final!"],
    )
    abertura = check_by_prefix(checks, "Abertura diferente")
    assert not abertura.ok
    assert "GENTE" in abertura.hint


def test_opening_check_passes_when_recent_hooks_start_differently():
    checks = check_seo(
        make_item(script_hook="Vazou o final de Wolverine!"),
        recent_hooks=["GENTE, olha isso", "Rockstar tá em apuros"],
    )
    assert check_by_prefix(checks, "Abertura diferente").ok


def test_missing_cta_fails():
    assert not check_by_prefix(check_seo(make_item(script_cta="")), "CTA").ok


def test_check_seo_accepts_sqlite_row(tmp_path):
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE t (script_description TEXT, script_hook TEXT, script_cta TEXT, game_name TEXT)"
    )
    conn.execute("INSERT INTO t VALUES (?, ?, ?, ?)", ("Texto #fyp #games #gaming #gta6", "Hook curto", "CTA", "Jogo"))
    row = conn.execute("SELECT * FROM t").fetchone()

    checks = check_seo(row)
    assert all(c.ok for c in checks)


def test_check_seo_tolerates_missing_columns():
    checks = check_seo({"script_hook": "Hook"})
    assert not check_by_prefix(checks, "Legenda").ok
