import logging
from types import SimpleNamespace

from xiaomusic.command_handler import CommandHandler
from xiaomusic.config import Config
from xiaomusic.utils.music_utils import get_duration_by_ffprobe


class DummyLog:
    def info(self, *_args, **_kwargs):
        pass

    def debug(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass


class DummyCompletedProcess:
    returncode = 1
    stdout = "broken.wav: Invalid data found when processing input\n"
    stderr = ""


def test_voice_alias_play_next_song_matches_when_idle():
    config = Config()
    handler = CommandHandler(config=config, log=DummyLog(), xiaomusic_instance=object())
    device = SimpleNamespace(is_playing=False, _pending_selection=None)

    opvalue, oparg = handler.match_cmd(device, "播放下一曲", ctrl_panel=False)

    assert (opvalue, oparg) == ("play_next", "")


def test_voice_alias_play_local_music_matches_even_with_old_keyword_config():
    config = Config()
    # Existing setting.json files may have been saved before this alias existed.
    # Built-in aliases must still be present after reinitializing from old config values.
    config.keywords_playlocal = "播放本地歌曲,本地播放歌曲"
    config.init()
    handler = CommandHandler(config=config, log=DummyLog(), xiaomusic_instance=object())
    device = SimpleNamespace(is_playing=False, _pending_selection=None)

    opvalue, oparg = handler.match_cmd(device, "播放本地音乐", ctrl_panel=False)

    assert (opvalue, oparg) == ("playlocal", "")


def test_ffprobe_non_json_failure_does_not_log_json_decode_noise(monkeypatch, caplog):
    from xiaomusic.utils import music_utils

    monkeypatch.setattr(music_utils.subprocess, "run", lambda *_args, **_kwargs: DummyCompletedProcess())

    with caplog.at_level(logging.WARNING):
        duration = get_duration_by_ffprobe("broken.wav", "/usr/bin")

    assert duration == 0
    assert "Expecting property name enclosed in double quotes" not in caplog.text
    assert "ffprobe failed" in caplog.text
