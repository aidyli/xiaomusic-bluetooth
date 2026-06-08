# Bluetooth Sidecar Systemd Image

This directory contains the build context for the Bluetooth sidecar image used by the XiaoMusic Bluetooth edition.

Published image:

```text
registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd
```

The image is a Debian bookworm based systemd container. It runs:

- systemd and D-Bus;
- BlueZ / `bluetooth.service`;
- PulseAudio with Bluetooth modules;
- `mpv` for audio playback;
- `sidecar-server.py`, a small HTTP bridge exposing `/health`, `/status`, `/scan`, `/connect`, `/play`, `/stop`, and `/disconnect`.

## Build

From the repository root:

```bash
docker build -t registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd   docker/bluetooth-sidecar-systemd
```

If you first build a local tag, retag it before pushing:

```bash
docker tag xiaomusic:bluetooth-sidecar-systemd   registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd
```

## Push

```bash
docker push registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd
```

## Runtime requirements

The sidecar needs access to the host USB Bluetooth adapter. The production compose uses:

```yaml
privileged: true
network_mode: host
cgroup: host
tmpfs:
  - /run
  - /run/lock
  - /tmp
volumes:
  - /sys/fs/cgroup:/sys/fs/cgroup:rw
  - /dev:/dev
  - /sys:/sys:ro
  - /run/udev:/run/udev:ro
  - ./bt-sidecar-systemd/state/bluetooth:/var/lib/bluetooth
environment:
  BT_TARGET_MAC: "44:F7:70:81:9C:C4"
  BT_BRIDGE_PORT: "58091"
```

`BT_TARGET_MAC` must be changed to the Bluetooth MAC address of your own target audio device. See the root README for scanning methods.
