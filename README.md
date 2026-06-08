# XiaoMusic 蓝牙立体声组合版

这是基于 [hanxi/xiaomusic](https://github.com/hanxi/xiaomusic) 的蓝牙立体声组合部署版本。

本仓库只保留与 **蓝牙 sidecar、蓝牙立体声组合输出、双音箱控制入口、部署/构建/验证** 相关的说明。XiaoMusic 原项目的完整功能、配置项、使用教程、开发文档和上游更新，请移步原项目：

> https://github.com/hanxi/xiaomusic

## 这个版本解决什么问题

原版 XiaoMusic 默认通过小爱音箱自身播放。这个蓝牙版本的目标是：

- 两只小爱音箱仍然作为语音控制入口；
- 实际音乐输出不再依赖某一只小爱音箱，而是统一输出到一个蓝牙“立体声组合”；
- 同一组内的设备共享播放状态、播放进度、播放列表和下一首任务；
- Web 设置页可以查看蓝牙 sidecar 状态，并执行扫描、连接、断开；
- 通过 Docker Compose 固化为可复现、可重建、可回滚的部署。

当前推荐部署形态是 **XiaoMusic 主容器 + 蓝牙 sidecar 容器**。

```text
小爱音箱 / Web 页面
  -> XiaoMusic 容器
  -> /host-scripts/call-xiaomi-bt-sidecar.sh {url}
  -> 127.0.0.1:58091 bt-audio-sidecar HTTP bridge
  -> sidecar 内 systemd + D-Bus + BlueZ + PulseAudio + mpv
  -> USB 蓝牙适配器
  -> 蓝牙立体声组合
```

## 当前镜像

推荐使用以下两个镜像 tag：

```text
registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v1
registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd
```

说明：

- `registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v1` 是发布到阿里云镜像仓库的主 XiaoMusic 蓝牙修复版镜像；
- `registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd` 是发布到阿里云镜像仓库的蓝牙 sidecar 镜像，由本仓库配套 sidecar 构建产物打包而来，不是上游官方镜像；
- 镜像 tag 同时作为部署版本标识，后续修复建议使用新 tag，不要覆盖已验证稳定 tag。

## 主要改动

### 1. 蓝牙组合播放后端

新增蓝牙组合播放命令配置：

```text
XIAOMUSIC_BLUETOOTH_COMBO_ENABLED=true
XIAOMUSIC_BLUETOOTH_COMBO_COMMAND=/host-scripts/call-xiaomi-bt-sidecar.sh {url}
XIAOMUSIC_BLUETOOTH_COMBO_STOP_COMMAND=/host-scripts/stop-xiaomi-bt-sidecar.sh
XIAOMUSIC_BLUETOOTH_COMBO_TIMEOUT_SEC=20
```

播放时 XiaoMusic 会调用 sidecar 播放脚本，把音频 URL 转交给 `bt-audio-sidecar`。停止播放时会调用 stop 脚本，停止 sidecar 内的 `mpv`。

### 2. 同组设备共享播放状态

同一 `group_list` 内的设备会共享：

- 当前播放歌曲；
- 当前播放列表；
- 播放进度；
- 是否正在播放；
- 播放 session；
- 下一首 / 预缓存 timer。

任一设备发起新播放时，会废弃组内旧 session，并取消旧的 next/prefetch timer，避免两只音箱各自保留旧任务。

### 3. 蓝牙组合全局播放 owner

蓝牙组合模式下，任意小爱音箱都只是控制入口。实际播放 owner 统一归并，WebSocket/API 返回当前真实播放 owner 的歌曲、歌单、状态和进度。

这样可以避免：

- A 音箱页面显示一首歌；
- B 音箱页面显示另一首歌；
- 旧设备 timer 自动切走当前播放；
- 停止命令只停止某一只设备而没有停止蓝牙输出。

### 4. Web 播放列表选择修复

Web 首页手动选择播放列表时，不再被 WebSocket 推送的“正在播放歌曲所在列表”强制拉回。

同时对线上歌单 `_online_*` 做了兜底处理：如果当前播放歌曲可以在本地歌单中定位，会优先回到对应本地歌单，避免页面长期卡在临时线上歌单。

### 5. Web 设置页蓝牙控制

设置页的蓝牙区域支持：

- 刷新 sidecar 状态；
- 扫描蓝牙设备；
- 选择设备；
- 连接；
- 断开；
- 显示 sidecar 返回的 JSON 结果。

请求会追加 cache-buster，避免浏览器或代理缓存导致按钮看似无效。

## 推荐 Docker Compose

部署目录示例：

```text
/volume2/docker/Docker/xiaomiai
```

推荐 `docker-compose.yaml`：

```yaml
services:
  bt-audio-sidecar:
    image: registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd
    container_name: bt-audio-sidecar
    privileged: true
    network_mode: host
    cgroup: host
    cgroup_parent: docker.slice
    restart: unless-stopped
    stop_signal: SIGRTMIN+3
    stop_grace_period: 30s
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
      PULSE_SERVER: "unix:/run/pulse/native"

  xiaomusic:
    image: registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v1
    container_name: xiaomusic
    restart: always
    network_mode: host
    depends_on:
      - bt-audio-sidecar
    environment:
      - XIAOMUSIC_PORT=58090
      - XIAOMUSIC_PUBLIC_PORT=58090
      - XIAOMUSIC_HOSTNAME=http://192.168.0.100
      - XIAOMUSIC_BLUETOOTH_COMBO_ENABLED=true
      - XIAOMUSIC_BLUETOOTH_COMBO_COMMAND=/host-scripts/call-xiaomi-bt-sidecar.sh {url}
      - XIAOMUSIC_BLUETOOTH_COMBO_STOP_COMMAND=/host-scripts/stop-xiaomi-bt-sidecar.sh
      - XIAOMUSIC_BLUETOOTH_COMBO_TIMEOUT_SEC=20
    volumes:
      - ./scripts:/host-scripts:ro
      - ./config:/app/conf:rw
      - ./cache:/app/cache:rw
      - /volume1/@home/pleach/Music:/app/music
```

请按自己的环境修改：

- `XIAOMUSIC_HOSTNAME`；
- 音乐目录挂载路径；
- `BT_TARGET_MAC`；
- 端口；
- 数据目录。

### `BT_TARGET_MAC` 是什么

`BT_TARGET_MAC` 是 **目标蓝牙音频设备的蓝牙 MAC 地址**，也就是 sidecar 最终要连接并输出声音的蓝牙设备地址。

在本示例中：

```yaml
BT_TARGET_MAC: "44:F7:70:81:9C:C4"
```

含义是：让 `bt-audio-sidecar` 连接蓝牙地址为 `44:F7:70:81:9C:C4` 的设备。这个地址在当前部署中对应“立体声组合”。

这个值不是固定值，换成你的蓝牙音箱、蓝牙功放、蓝牙耳机或其他 A2DP 接收设备时，需要改成你自己设备的 MAC 地址。

获取方式有三种：

#### 方法 1：通过 XiaoMusic 设置页扫描

1. 打开 XiaoMusic 设置页；
2. 进入“蓝牙播放”区域；
3. 先让目标蓝牙设备进入可发现/配对模式；
4. 点击“扫描”；
5. 在扫描结果或设备下拉框中找到目标设备；
6. 记录括号里的地址，例如：

```text
立体声组合 (44:F7:70:81:9C:C4)
```

然后把 compose 中的 `BT_TARGET_MAC` 改成这个地址。

#### 方法 2：直接调用 sidecar 扫描接口

扫描前先让目标设备进入可发现/配对模式，然后执行：

```bash
curl -fsS 'http://127.0.0.1:58091/scan?seconds=90'
```

扫描结果里通常会出现类似：

```text
Device 44:F7:70:81:9C:C4 立体声组合
```

其中 `44:F7:70:81:9C:C4` 就是要填入 `BT_TARGET_MAC` 的值。

#### 方法 3：进入 sidecar 容器用 `bluetoothctl`

```bash
docker exec -it bt-audio-sidecar bluetoothctl
```

在交互界面中执行：

```text
power on
agent on
default-agent
scan on
```

等待目标设备出现：

```text
[NEW] Device 44:F7:70:81:9C:C4 立体声组合
```

记录 `Device` 后面的地址，然后执行：

```text
scan off
quit
```

如果设备已经配对过，也可以查看已知设备：

```bash
docker exec bt-audio-sidecar bluetoothctl devices
```

注意事项：

- 蓝牙 MAC 地址格式通常是六组十六进制数，例如 `AA:BB:CC:DD:EE:FF`；
- 扫描前必须让目标设备进入可发现/配对模式；
- 建议扫描 60-120 秒，短扫描可能错过设备的可发现窗口；
- 多个设备同时可见时，要根据设备名称确认不要填错；
- 修改 `BT_TARGET_MAC` 后需要重建 sidecar 服务：

```bash
cd /volume2/docker/Docker/xiaomiai
docker compose up -d --force-recreate bt-audio-sidecar
```

## 持久化目录

建议部署目录结构：

```text
xiaomiai/
├── docker-compose.yaml
├── scripts/
│   ├── call-xiaomi-bt-sidecar.sh
│   ├── stop-xiaomi-bt-sidecar.sh
│   ├── connect-xiaomi-bt-sidecar.sh
│   └── disconnect-xiaomi-bt-sidecar.sh
├── config/
│   └── setting.json
├── cache/
└── bt-sidecar-systemd/
    └── state/
        └── bluetooth/
```

关键持久化：

```text
./config:/app/conf:rw
./cache:/app/cache:rw
./bt-sidecar-systemd/state/bluetooth:/var/lib/bluetooth
```

其中 `/var/lib/bluetooth` 非常重要，用于保存 BlueZ 配对和 trust 状态。否则每次重建 sidecar 后可能需要重新扫描、配对、连接。

## sidecar 脚本

### `call-xiaomi-bt-sidecar.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

URL=${1:?missing audio url}
BASE=${BT_SIDECAR_BASE:-http://127.0.0.1:58091}

ENC=$(python3 - <<'PY' "$URL"
import sys, urllib.parse
print(urllib.parse.quote(sys.argv[1], safe=''))
PY
)

wget -qO- --timeout=20 "$BASE/play?url=$ENC"
```

### `stop-xiaomi-bt-sidecar.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

BASE=${BT_SIDECAR_BASE:-http://127.0.0.1:58091}
wget -qO- --timeout=10 "$BASE/stop"
```

### `connect-xiaomi-bt-sidecar.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

BASE=${BT_SIDECAR_BASE:-http://127.0.0.1:58091}
wget -qO- --timeout=60 "$BASE/connect?async=0"
```

### `disconnect-xiaomi-bt-sidecar.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

BASE=${BT_SIDECAR_BASE:-http://127.0.0.1:58091}
wget -qO- --timeout=20 "$BASE/disconnect"
```

## 蓝牙 sidecar 镜像来源

`registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd` 是发布到阿里云镜像仓库的 Debian systemd 蓝牙 sidecar 镜像。它由本地 sidecar 构建目录构建后重新打 tag 并推送到阿里云镜像仓库。

它包含：

- Debian bookworm slim；
- systemd；
- D-Bus；
- BlueZ / `bluetooth.service`；
- PulseAudio；
- `pulseaudio-module-bluetooth`；
- `mpv`；
- Python HTTP bridge。

它的职责是独占 USB 蓝牙适配器，连接目标蓝牙音频设备，并把 XiaoMusic 传入的音频 URL 播放到 BlueZ A2DP sink。

### 构建目录

sidecar 构建上下文已经随本仓库一起提交，路径为：

```text
docker/bluetooth-sidecar-systemd/
```

目录内容：

```text
docker/bluetooth-sidecar-systemd/
├── Dockerfile
├── README.md
├── sidecar-server.py
├── pulse-system.pa
├── bt-prep.service
├── bt-pulseaudio.service
├── bt-sidecar-bridge.service
└── docker-compose.yaml
```

其中 `docker-compose.yaml` 是 sidecar 单独调试/参考用例，生产部署仍建议使用上文的双容器 compose。

### Dockerfile 核心内容

```dockerfile
FROM debian:bookworm-slim

ENV container=docker
ENV DEBIAN_FRONTEND=noninteractive

STOPSIGNAL SIGRTMIN+3

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    systemd systemd-sysv dbus \
    bluez bluez-tools rfkill usbutils procps psmisc \
    pulseaudio pulseaudio-module-bluetooth pulseaudio-utils \
    mpv ffmpeg ca-certificates python3 curl kmod \
 && rm -rf /var/lib/apt/lists/* \
 && systemctl set-default multi-user.target \
 && systemctl enable bluetooth.service

COPY sidecar-server.py /usr/local/bin/sidecar-server.py
COPY pulse-system.pa /etc/pulse/system.pa
COPY bt-prep.service /etc/systemd/system/bt-prep.service
COPY bt-pulseaudio.service /etc/systemd/system/bt-pulseaudio.service
COPY bt-sidecar-bridge.service /etc/systemd/system/bt-sidecar-bridge.service

RUN chmod +x /usr/local/bin/sidecar-server.py \
 && systemctl enable bt-prep.service bt-pulseaudio.service bt-sidecar-bridge.service

CMD ["/sbin/init"]
```

### 构建 sidecar 镜像

```bash
# 从仓库根目录执行
docker build -t registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd \
  docker/bluetooth-sidecar-systemd
```

如需从本地 tag 转成阿里云镜像仓库 tag：

```bash
docker tag xiaomusic:bluetooth-sidecar-systemd \
  registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd
```

推送到阿里云镜像仓库：

```bash
docker push registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd
```

### 打包 sidecar 镜像

```bash
docker save registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd | gzip > xiaomusic-bluetooth-sidecar-systemd.tar.gz
sha256sum xiaomusic-bluetooth-sidecar-systemd.tar.gz
```

### 导入 sidecar 镜像

```bash
gunzip -c xiaomusic-bluetooth-sidecar-systemd.tar.gz | docker load
```

## 主 XiaoMusic 蓝牙镜像构建

在本仓库根目录执行：

```bash
docker build -t registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v1 .
```

如需从本地蓝牙修复 tag 转成阿里云镜像仓库 tag：

```bash
docker tag xiaomusic:bluetooth-combo-global-playback-api-owner-20260530-r8 \
  registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v1
```

推送到阿里云镜像仓库：

```bash
docker push registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v1
```

打包：

```bash
docker save registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v1 \
  | gzip > xiaomusic-bluetooth-v1.tar.gz

sha256sum xiaomusic-bluetooth-v1.tar.gz
```

导入：

```bash
gunzip -c xiaomusic-bluetooth-v1.tar.gz | docker load
```

## 部署

```bash
cd /volume2/docker/Docker/xiaomiai
docker compose up -d
```

强制重建：

```bash
docker compose up -d --force-recreate
```

查看状态：

```bash
docker compose ps
docker logs --tail=100 bt-audio-sidecar
docker logs --tail=100 xiaomusic
```

## sidecar HTTP API

默认监听：

```text
127.0.0.1:58091
```

接口：

```text
GET /health
GET /status
GET /scan?seconds=90
GET /connect?async=0
GET /play?url=<encoded-url>
GET /stop
GET /disconnect
```

### `/health`

用于检查 sidecar 是否可用，是否已经存在蓝牙 A2DP sink。

示例：

```bash
curl -fsS http://127.0.0.1:58091/health
```

可能返回：

```json
{
  "ok": true,
  "sink": "bluez_sink.44_F7_70_81_9C_C4.a2dp_sink",
  "scan_running": false,
  "connect_running": false
}
```

### `/status`

用于查看蓝牙设备、sink、连接任务状态。

```bash
curl -fsS http://127.0.0.1:58091/status
```

### `/scan`

扫描蓝牙设备。

```bash
curl -fsS 'http://127.0.0.1:58091/scan?seconds=90'
```

注意：扫描前请先让蓝牙音频设备进入可发现/配对模式。建议扫描 60-120 秒，短扫描可能错过可发现窗口。

### `/connect`

连接目标设备。

```bash
curl -fsS 'http://127.0.0.1:58091/connect?async=0'
```

### `/play`

播放音频 URL。

```bash
docker exec xiaomusic /host-scripts/call-xiaomi-bt-sidecar.sh \
  'av://lavfi:sine=frequency=880:duration=5'
```

### `/stop`

停止 sidecar 内当前 `mpv` 播放。

```bash
docker exec xiaomusic /host-scripts/stop-xiaomi-bt-sidecar.sh
```

## 验证清单

部署后建议按顺序验证：

```bash
# 1. 容器状态
docker compose ps

# 2. sidecar health
curl -fsS http://127.0.0.1:58091/health

# 3. sidecar status
curl -fsS http://127.0.0.1:58091/status

# 4. XiaoMusic 代理 API
curl -fsS 'http://127.0.0.1:58090/api/bluetooth/status?_=verify'

# 5. 从 XiaoMusic 容器调用 sidecar 播放测试音
docker exec xiaomusic /host-scripts/call-xiaomi-bt-sidecar.sh \
  'av://lavfi:sine=frequency=880:duration=5'

# 6. 停止测试音
docker exec xiaomusic /host-scripts/stop-xiaomi-bt-sidecar.sh
```

如果 `/health` 中能看到类似下面的 sink，说明 A2DP 输出已经就绪：

```text
bluez_sink.44_F7_70_81_9C_C4.a2dp_sink
```

## 蓝牙扫描与配对注意事项

- 扫描前必须让目标蓝牙设备进入可发现/配对模式；
- 建议扫描 60-120 秒；
- 如果短扫描找不到设备，不代表 sidecar 异常；
- 如果重建容器后无法连接，先检查 `./bt-sidecar-systemd/state/bluetooth` 是否持久化；
- sidecar 接管 USB 蓝牙适配器时，宿主机 BlueZ 或旧的宿主机 bridge 不应同时接管同一个 dongle；
- 如果曾经用宿主机 BlueZ 连接过同一个设备，迁移到 sidecar 后建议确认宿主机上的旧蓝牙服务/旧 bridge 不再抢占适配器。

## 常见问题

### 设置页保存后又变成旧脚本怎么办？

检查 `config/setting.json` 里的配置是否被覆盖成旧脚本。

正确值应类似：

```json
{
  "bluetooth_combo_enabled": "true",
  "bluetooth_combo_command": "/host-scripts/call-xiaomi-bt-sidecar.sh {url}",
  "bluetooth_combo_stop_command": "/host-scripts/stop-xiaomi-bt-sidecar.sh",
  "bluetooth_combo_timeout_sec": 20
}
```

如果语音插件需要通过自定义口令执行，还要确认 `active_cmd` 中包含对应 `exec#...` 项。

### sidecar 已连接但没有声音怎么办？

按顺序检查：

```bash
curl -fsS http://127.0.0.1:58091/health
curl -fsS http://127.0.0.1:58091/status
docker exec xiaomusic /host-scripts/call-xiaomi-bt-sidecar.sh \
  'av://lavfi:sine=frequency=880:duration=5'
docker logs --tail=200 bt-audio-sidecar
```

重点看：

- 是否有 `bluez_sink.*.a2dp_sink`；
- `mpv` 是否启动；
- 目标设备是否 `Connected: yes`；
- `BT_TARGET_MAC` 是否正确。

### 为什么 `/sys` 要只读挂载？

生产验证中，`/sys:/sys` 读写挂载曾导致 BlueZ adapter/GATT 初始化异常。推荐：

```yaml
- /sys:/sys:ro
```

### 为什么需要 `network_mode: host`？

XiaoMusic 和 sidecar 都使用 host network 后，XiaoMusic 容器内访问：

```text
127.0.0.1:58091
```

就是访问宿主机网络命名空间中的 sidecar HTTP bridge。这样脚本和 API 都更简单，也避免 Docker bridge 网络下音频/蓝牙服务发现问题。

## 回滚建议

不要覆盖已验证镜像 tag。修复或实验请使用新 tag。

建议保留：

```text
xiaomusic:bluetooth-combo-stable-20260526
registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v1
registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd
```

回滚时只需要改 compose 中的主镜像 tag，然后重建：

```bash
cd /volume2/docker/Docker/xiaomiai
docker compose up -d --force-recreate xiaomusic
```

## 上游项目

本仓库不再重复维护 XiaoMusic 原项目完整 README。

如需查看原版 XiaoMusic 的完整说明、功能介绍、配置教程、接口文档和上游更新，请访问：

> https://github.com/hanxi/xiaomusic
