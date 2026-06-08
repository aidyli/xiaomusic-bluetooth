import asyncio
from types import SimpleNamespace

from xiaomusic.config import Config, Device
from xiaomusic.device_player import XiaoMusicDevice


class _FakeResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return '{"ok": true, "action": "play", "sink": "bluez_sink.test"}'


class _FakeSession:
    def __init__(self, calls):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url, params=None):
        self.calls.append((url, params))
        return _FakeResponse()


class _FakeXiaoMusic:
    def __init__(self, config):
        self.config = config
        self.log = SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
            error=lambda *args, **kwargs: None,
            exception=lambda *args, **kwargs: None,
        )
        self.auth_manager = None


def _make_player(config):
    device = Device(did="1", device_id="dev1", name="speaker")
    return XiaoMusicDevice(_FakeXiaoMusic(config), device, "group")


def test_bluetooth_sidecar_play_uses_http_api(monkeypatch):
    config = Config(
        bluetooth_combo_enabled=True,
        bluetooth_sidecar_base="http://sidecar.local:58091/",
        bluetooth_sidecar_timeout_sec=7,
        bluetooth_combo_command="legacy-command {url}",
    )
    player = _make_player(config)
    calls = []

    monkeypatch.setattr(
        "xiaomusic.device_player.aiohttp.ClientSession",
        lambda timeout=None: _FakeSession(calls),
    )

    result = asyncio.run(player._run_bluetooth_sidecar_play("http://music/a b.mp3", "song"))

    assert result["bluetooth_sidecar"] is True
    assert calls == [
        ("http://sidecar.local:58091/stop", None),
        ("http://sidecar.local:58091/play", {"url": "http://music/a b.mp3"}),
    ]


def test_bluetooth_sidecar_stop_uses_http_api(monkeypatch):
    config = Config(
        bluetooth_combo_enabled=True,
        bluetooth_sidecar_base="http://127.0.0.1:58091",
        bluetooth_sidecar_timeout_sec=9,
        bluetooth_combo_stop_command="legacy-stop",
    )
    player = _make_player(config)
    calls = []

    monkeypatch.setattr(
        "xiaomusic.device_player.aiohttp.ClientSession",
        lambda timeout=None: _FakeSession(calls),
    )

    result = asyncio.run(player._run_bluetooth_sidecar_stop())

    assert result["bluetooth_sidecar_stop"] is True
    assert calls == [("http://127.0.0.1:58091/stop", None)]
