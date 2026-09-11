"""Testes da capa (thumbnail): escolha do frame de fundo, comando do Remotion
e a garantia de que uma capa quebrada nunca derruba o vídeo."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from video_gen.cover import background_frame, render_cover


def _spec(background: str = "", **extra) -> dict:
    spec = {
        "itemId": 7,
        "title": "t",
        "source": "ign",
        "hook": "Hook de teste",
        "backgroundVideoPath": background,
        "badge": "VAZOU",
        "gameName": "Some Game",
    }
    spec.update(extra)
    return spec


def test_background_frame_is_zero_without_clip():
    assert background_frame(_spec()) == 0
    assert background_frame({}) == 0


def test_background_frame_samples_a_quarter_into_the_clip(tmp_path):
    with patch("video_gen.cover._probe_duration_seconds", return_value=60.0):
        # 25% de 60s = 15s -> frame 450 (30fps), nunca o começo do trailer
        assert background_frame(_spec("background/g.mp4"), public_dir=tmp_path) == 450


def test_background_frame_stays_inside_short_clips(tmp_path):
    with patch("video_gen.cover._probe_duration_seconds", return_value=2.0):
        frame = background_frame(_spec("background/g.mp4"), public_dir=tmp_path)
    assert 0 < frame <= int(1.5 * 30)


def test_background_frame_falls_back_to_zero_when_probe_fails(tmp_path):
    with patch("video_gen.cover._probe_duration_seconds", return_value=None):
        assert background_frame(_spec("background/g.mp4"), public_dir=tmp_path) == 0


def _write_spec(tmp_path: Path, spec: dict) -> Path:
    path = tmp_path / "item_7.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def test_render_cover_calls_remotion_still_with_frame(tmp_path, monkeypatch):
    import video_gen.cover as cover_module

    monkeypatch.setattr(cover_module, "COVERS_DIR", tmp_path / "covers")
    spec_path = _write_spec(tmp_path, _spec())

    ok = MagicMock(returncode=0, stderr="")
    with patch("video_gen.cover.subprocess.run", return_value=ok) as run:
        output = render_cover(spec_path, item_id=7)

    cmd = run.call_args[0][0]
    assert cmd[:4] == ["npx", "remotion", "still", "NewsCover"]
    assert f"--props={spec_path}" in cmd
    assert "--frame=0" in cmd  # spec sem fundo
    assert output == tmp_path / "covers" / "item_7.png"


def test_render_cover_raises_when_remotion_fails(tmp_path, monkeypatch):
    import video_gen.cover as cover_module

    monkeypatch.setattr(cover_module, "COVERS_DIR", tmp_path / "covers")
    spec_path = _write_spec(tmp_path, _spec())

    fail = MagicMock(returncode=1, stderr="boom")
    with patch("video_gen.cover.subprocess.run", return_value=fail):
        with pytest.raises(RuntimeError):
            render_cover(spec_path, item_id=7)


def test_failed_cover_does_not_break_the_video(tmp_path):
    """Regra: capa é acessório. Se o still falhar, generate_video_for_item
    continua devolvendo o vídeo (sem a chave cover_path)."""
    from video_gen.assembler import generate_video_for_item

    class Row(dict):
        def keys(self):
            return list(super().keys())

    row = Row(
        {
            "id": 7,
            "title": "t",
            "source": "ign",
            "script_hook": "h",
            "script_body": "b",
            "script_cta": "c",
            "game_name": "Some Game",
            "matched_keywords": "leak",
            "script_pronunciations": "",
        }
    )
    speech = MagicMock(audio_path=tmp_path / "a.mp3", words=[], spoken_text="h b c")
    (tmp_path / "a.mp3").write_bytes(b"x")

    with (
        patch("video_gen.assembler.resolve_media", return_value=(None, None)),
        patch("video_gen.assembler.synthesize_speech", return_value=speech),
        patch("video_gen.assembler._publish_asset", return_value="audio/a.mp3"),
        patch("video_gen.assembler.write_spec", return_value=tmp_path / "spec.json"),
        patch("video_gen.assembler.render_video", return_value=tmp_path / "v.mp4"),
        patch("video_gen.assembler.render_cover", side_effect=RuntimeError("still falhou")),
    ):
        result = generate_video_for_item(row, render=True)

    assert result["video_path"] == str(tmp_path / "v.mp4")
    assert "cover_path" not in result


def test_cover_path_is_returned_when_render_succeeds(tmp_path):
    from video_gen.assembler import generate_video_for_item

    class Row(dict):
        def keys(self):
            return list(super().keys())

    row = Row(
        {
            "id": 7,
            "title": "t",
            "source": "ign",
            "script_hook": "h",
            "script_body": "b",
            "script_cta": "c",
            "game_name": "Some Game",
            "matched_keywords": "",
            "script_pronunciations": "",
        }
    )
    speech = MagicMock(audio_path=tmp_path / "a.mp3", words=[], spoken_text="h b c")
    (tmp_path / "a.mp3").write_bytes(b"x")

    with (
        patch("video_gen.assembler.resolve_media", return_value=(None, None)),
        patch("video_gen.assembler.synthesize_speech", return_value=speech),
        patch("video_gen.assembler._publish_asset", return_value="audio/a.mp3"),
        patch("video_gen.assembler.write_spec", return_value=tmp_path / "spec.json"),
        patch("video_gen.assembler.render_video", return_value=tmp_path / "v.mp4"),
        patch("video_gen.assembler.render_cover", return_value=tmp_path / "c.png"),
    ):
        result = generate_video_for_item(row, render=True)

    assert result["cover_path"] == str(tmp_path / "c.png")


def test_spec_carries_game_name_for_the_cover():
    from video_gen.assembler import build_video_spec

    spec = build_video_spec(
        item_id=1,
        hook="h",
        body="b",
        cta="c",
        audio_relative_path="audio/item_1.mp3",
        words=[],
        source="ign",
        title="T",
        game_name="Grand Theft Auto VI",
    )
    assert spec["gameName"] == "Grand Theft Auto VI"
