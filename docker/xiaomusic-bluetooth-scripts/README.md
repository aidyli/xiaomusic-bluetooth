# XiaoMusic Bluetooth helper scripts

These scripts are packaged into the main XiaoMusic Bluetooth image at:

```text
/app/bin/
```

They call the Bluetooth sidecar HTTP bridge. The default sidecar endpoint is suitable for `network_mode: host` deployments:

```text
BT_SIDECAR_BASE=http://127.0.0.1:58091
```

For Docker bridge networking or a remote sidecar, override it in compose:

```yaml
environment:
  - BT_SIDECAR_BASE=http://bt-audio-sidecar:58091
```

Supported environment variables:

- `BT_SIDECAR_BASE`: sidecar HTTP base URL, default `http://127.0.0.1:58091`.
- `BT_SIDECAR_TIMEOUT`: play/stop/disconnect timeout in seconds, default `20`.
- `BT_SIDECAR_CONNECT_TIMEOUT`: connect timeout in seconds, default `60`.

Main XiaoMusic config should point to the packaged scripts:

```yaml
XIAOMUSIC_BLUETOOTH_COMBO_COMMAND=/app/bin/call-xiaomi-bt-sidecar.sh {url}
XIAOMUSIC_BLUETOOTH_COMBO_STOP_COMMAND=/app/bin/stop-xiaomi-bt-sidecar.sh
```
