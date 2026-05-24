import time
from types import SimpleNamespace

from xiaomusic.const import PLAY_TYPE_RND
from xiaomusic.device_player import XiaoMusicDevice
from xiaomusic.music_library import MusicLibrary


class DummyMusicLibrary:
    def __init__(self, songs):
        self.music_list = {"所有歌曲": songs}

    @staticmethod
    def is_online_music(_list_name):
        return False

    @staticmethod
    def is_music_exist(_name):
        return True


class DummyLog:
    def info(self, *_args, **_kwargs):
        pass

    def debug(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass


def make_device(songs, old_songs=None):
    device = XiaoMusicDevice.__new__(XiaoMusicDevice)
    device.device = SimpleNamespace(
        cur_playlist="所有歌曲",
        play_type=PLAY_TYPE_RND,
        cur_music=songs[0],
        playlist2music={},
    )
    device.xiaomusic = SimpleNamespace(music_library=DummyMusicLibrary(songs))
    device.log = DummyLog()
    device._play_list = list(old_songs if old_songs is not None else songs)
    return device


def test_large_random_playlist_incremental_update_is_linear_time():
    songs = [f"song-{i}" for i in range(30000)]
    # Simulate a large existing shuffled/current list with one deleted song and one new song.
    old_songs = songs[:-1] + ["deleted-song"]
    latest_songs = songs + ["new-song"]
    device = make_device(latest_songs, old_songs=old_songs)

    started = time.perf_counter()
    device.update_playlist()
    elapsed = time.perf_counter() - started

    assert "deleted-song" not in device._play_list
    assert "new-song" in device._play_list
    # The previous implementation used list membership inside list comprehensions,
    # making this O(n^2) and taking many seconds on large libraries.
    assert elapsed < 1.0


def test_find_real_music_name_returns_exact_match_without_scanning_large_library():
    config = SimpleNamespace(enable_fuzzy_match=True, fuzzy_match_cutoff=0.6)
    library = MusicLibrary.__new__(MusicLibrary)
    library.config = config
    library.log = DummyLog()
    library.all_music = {f"song-{i}": f"/music/song-{i}.mp3" for i in range(50000)}
    library.all_music["音乐小屋"] = "/music/音乐小屋.wma"
    library._extra_index_search = {}

    started = time.perf_counter()
    result = library.find_real_music_name("音乐小屋", n=10)
    elapsed = time.perf_counter() - started

    assert result == ["音乐小屋"]
    assert elapsed < 0.2
