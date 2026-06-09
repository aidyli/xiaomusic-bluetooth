# XiaoMusic Bluetooth V5 部署说明

本文记录 `registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v5` 及配套 sidecar 的功能、构建、部署、验证与回滚方式。

## 目标

V5 在 V3/V4 的蓝牙 sidecar 播放基础上，增加“任意蓝牙音频设备”控制能力：

```text
XiaoMusic Web/UI
  -> /api/bluetooth/status /scan /connect?address=... /disconnect?address=...
  -> bt-audio-sidecar HTTP bridge
  -> BlueZ + PulseAudio + mpv
  -> 当前选择的蓝牙 A2DP 音频设备
```

核心变化：

- 不再只围绕固定 `BT_TARGET_MAC` 连接；`/connect`、`/disconnect`、`/status`、`/play` 支持 `address` 参数。
- sidecar 维护 `current_address`，播放时优先使用当前连接设备对应的 `bluez_sink.<MAC>.a2dp_sink`。
- `/status` 返回 `devices[]`，包含设备地址、名称、是否配对/信任/连接、是否具备音频输出 profile。
- 设置页实时扫描默认 30 秒，并显示扫描倒计时。
- UI 不再显示部署版本；镜像 tag 作为版本标识。
- 播放列表 UI 修复：当后端返回 `所有歌曲/全部/所有电台` 这类聚合歌单时，前端会根据当前播放歌曲反查具体歌单。

## 镜像

主镜像：

```text
registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v5
```

sidecar 镜像：

```text
registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd-v5
```

## 配置项

推荐通过环境变量配置：

```yaml
- XIAOMUSIC_BLUETOOTH_COMBO_ENABLED=true
- XIAOMUSIC_BLUETOOTH_SIDECAR_BASE=http://127.0.0.1:58091
- XIAOMUSIC_BLUETOOTH_SIDECAR_TIMEOUT_SEC=20
```

sidecar 可保留默认目标，用作未显式选择设备时的 fallback：

```yaml
- BT_TARGET_MAC=44:F7:70:81:9C:C4
- BT_BRIDGE_PORT=58091
```

说明：

- `BT_TARGET_MAC` 只是默认/fallback，不再限制 UI 只能连接这一个设备。
- 点击设置页“连接所选设备”时，XiaoMusic 会调用 `/api/bluetooth/connect?address=<MAC>&async=0`。
- 当前连接成功的设备会成为 sidecar 的 `current_address`；后续播放走该设备的 A2DP sink。

## 生产 compose 要点

```yaml
bt-audio-sidecar:
  image: registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd-v5
  container_name: bt-audio-sidecar
  restart: always
  network_mode: host
  privileged: true
  environment:
    - BT_TARGET_MAC=44:F7:70:81:9C:C4
    - BT_BRIDGE_PORT=58091

xiaomusic:
  image: registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v5
  container_name: xiaomusic
  restart: always
  network_mode: host
  depends_on:
    - bt-audio-sidecar
  environment:
    - XIAOMUSIC_PORT=58090
    - XIAOMUSIC_PUBLIC_PORT=58090
    - XIAOMUSIC_BLUETOOTH_COMBO_ENABLED=true
    - XIAOMUSIC_BLUETOOTH_SIDECAR_BASE=http://127.0.0.1:58091
    - XIAOMUSIC_BLUETOOTH_SIDECAR_TIMEOUT_SEC=20
```

`network_mode: host` 很重要：XiaoMusic 容器内访问 `127.0.0.1:58091` 即访问 sidecar HTTP bridge。

## UI 操作流程

1. 打开设置页 → 高级配置 → 蓝牙播放。
2. 让目标蓝牙音箱/耳机进入可发现或配对模式。
3. 点击“实时扫描蓝牙设备”。默认扫描 30 秒，页面会实时显示倒计时。
4. 在“扫描/已知蓝牙设备”下拉框选择目标设备。
5. 点击“连接所选设备”。
6. 刷新状态，确认：
   - `connected: true`
   - `audio_sink: true`
   - `sink` 类似 `bluez_sink.XX_XX_XX_XX_XX_XX.a2dp_sink`

注意：能扫描到不等于可作为音频输出。手机、手环、遥控器、BLE 传感器等可能没有 A2DP Audio Sink profile；这类设备即使可见，也不能作为 XiaoMusic 输出设备。

## 构建与推送

主镜像：

```bash
docker build -t registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v5 .
docker push registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v5
```

sidecar 镜像：

```bash
docker build -t registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd-v5 docker/bluetooth-sidecar-systemd
docker push registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd-v5
```

本次生产环境也可以从已验证本地镜像 retag 后推送：

```bash
docker tag xiaomusic:bluetooth-combo-4.2 registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v5
docker tag xiaomusic:bluetooth-sidecar-systemd-4.2 registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd-v5
docker push registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v5
docker push registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd-v5
```

## 验证

### 1. 镜像与容器

```bash
docker ps --filter name=^/xiaomusic$ --format '{{.Names}} {{.Image}} {{.Status}}'
docker ps --filter name=^/bt-audio-sidecar$ --format '{{.Names}} {{.Image}} {{.Status}}'
```

期望：

```text
xiaomusic registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v5 Up ...
bt-audio-sidecar registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd-v5 Up ...
```

### 2. Web 与 API

```bash
curl -fsS http://127.0.0.1:58090/ >/dev/null
curl -fsS 'http://127.0.0.1:58090/api/bluetooth/status?_=verify'
curl -fsS http://127.0.0.1:58091/health
```

期望：

- `ok: true`
- `/status` 包含 `current_address`、`default_address`、`devices[]`
- 设置页 HTML 包含 `setting.js?version=4.2` 或后续等价缓存版本
- UI 不包含可见 `部署版本`

### 3. 指定设备连接

```bash
curl -fsS 'http://127.0.0.1:58090/api/bluetooth/connect?address=C3%3A37%3AD8%3A2C%3ABF%3A1F&async=0'
```

连接成功时应看到：

```text
connected: true
sink: bluez_sink.C3_37_D8_2C_BF_1F.a2dp_sink
```

### 4. 播放测试

```bash
curl -fsS 'http://127.0.0.1:58091/play?address=C3%3A37%3AD8%3A2C%3ABF%3A1F&url=av%3A%2F%2Flavfi%3Asine%3Dfrequency%3D660%3Aduration%3D3'
curl -fsS 'http://127.0.0.1:58091/stop'
```

## 回滚

如需回滚到本地 4.2：

```yaml
image: xiaomusic:bluetooth-combo-4.2
image: xiaomusic:bluetooth-sidecar-systemd-4.2
```

如需回滚到旧阿里云 v4：

```yaml
image: registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v4
image: registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd
```

回滚后执行：

```bash
docker compose up -d --force-recreate bt-audio-sidecar xiaomusic
```
