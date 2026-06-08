# XiaoMusic Bluetooth V3 部署说明

本文记录 `registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v3` 的构建、部署、配置和验证方式。

## 目标

V3 的目标是把蓝牙立体声组合输出从“脚本命令模板”升级为 XiaoMusic 内部直接调用 sidecar HTTP API：

```text
XiaoMusic Python 代码
  -> http://127.0.0.1:58091/play /stop /status /connect /disconnect
  -> bt-audio-sidecar
  -> BlueZ + PulseAudio + mpv
  -> 蓝牙立体声组合
```

这样可以减少设置页保存后把播放输出方式覆盖回旧脚本的风险，也让主镜像 tag 本身成为明确版本标识。

## 镜像

主镜像：

```text
registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v3
```

sidecar 镜像：

```text
registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:bluetooth-sidecar-systemd
```

生产验证时主镜像 ID：

```text
sha256:316be174e080f6665e39657ad3a7d9b10cdadee96d1e298e4ec1710b81ee9278
```

## V3 配置项

推荐通过环境变量配置：

```yaml
- XIAOMUSIC_BLUETOOTH_COMBO_ENABLED=true
- XIAOMUSIC_BLUETOOTH_SIDECAR_BASE=http://127.0.0.1:58091
- XIAOMUSIC_BLUETOOTH_SIDECAR_TIMEOUT_SEC=20
```

持久化 `config/setting.json` 中也应保持同等语义：

```json
{
  "bluetooth_combo_enabled": "true",
  "bluetooth_sidecar_base": "http://127.0.0.1:58091",
  "bluetooth_sidecar_timeout_sec": 20,
  "bluetooth_combo_command": "",
  "bluetooth_combo_stop_command": ""
}
```

说明：

- `bluetooth_combo_enabled=true`：启用蓝牙组合输出。
- `bluetooth_sidecar_base`：XiaoMusic 调用 sidecar 的 HTTP base URL。
- `bluetooth_sidecar_timeout_sec`：HTTP 调用超时时间。
- `bluetooth_combo_command` / `bluetooth_combo_stop_command`：V3 默认留空，避免回落到旧脚本路径。

## 生产 compose 要点

生产部署目录示例：

```text
/volume2/docker/Docker/xiaomiai
```

主服务应使用：

```yaml
xiaomusic:
  image: registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v3
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
  volumes:
    - ./config:/app/conf:rw
    - ./cache:/app/cache:rw
    - /path/to/Music:/app/music
```

`network_mode: host` 很重要：XiaoMusic 和 sidecar 都在 host network 下时，主容器内访问 `127.0.0.1:58091` 就是访问 sidecar HTTP bridge。

## 构建

普通构建：

```bash
docker build -t registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v3 .
```

在旧 Docker builder 或需要强制 linux/amd64 时，可使用仓库内的 `Dockerfile.v3-amd64`：

```bash
docker build -f Dockerfile.v3-amd64 \
  -t registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v3 .
```

推送：

```bash
docker push registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v3
```

打包：

```bash
docker save registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v3 \
  | gzip > xiaomusic-bluetooth-v3.tar.gz
sha256sum xiaomusic-bluetooth-v3.tar.gz
```

## 部署步骤

建议先备份：

```bash
cd /volume2/docker/Docker/xiaomiai
mkdir -p backups/v3-redeploy-$(date +%Y%m%d-%H%M%S)
cp -a docker-compose.yaml config/setting.json backups/v3-redeploy-*/
```

然后部署：

```bash
cd /volume2/docker/Docker/xiaomiai
docker compose pull xiaomusic
docker compose up -d --force-recreate xiaomusic
```

如果旧容器被不同 compose/service 残留占用，可先确认后移除旧 `xiaomusic` 容器，再 `docker compose up -d`。

## 验证

### 1. 运行镜像

```bash
docker inspect xiaomusic --format 'RUNNING_IMAGE={{.Config.Image}} IMAGE_ID={{.Image}} STATUS={{.State.Status}}'
```

期望：

```text
RUNNING_IMAGE=registry.cn-hangzhou.aliyuncs.com/aliyun_nas/xiaomusic-bluetooth:v3
STATUS=running
```

### 2. 运行时配置

```bash
docker exec xiaomusic python3 - <<'PY'
from xiaomusic.config import Config
c = Config.from_options('/app/conf/setting.json')
print(c.bluetooth_combo_enabled)
print(c.bluetooth_sidecar_base)
print(c.bluetooth_sidecar_timeout_sec)
print(repr(c.bluetooth_combo_command))
print(repr(c.bluetooth_combo_stop_command))
PY
```

期望：

```text
True
http://127.0.0.1:58091
20
''
''
```

### 3. Web 与蓝牙 API

```bash
curl -fsS http://127.0.0.1:58090/ >/dev/null
curl -fsS 'http://127.0.0.1:58090/api/bluetooth/status?_=verify'
curl -fsS http://127.0.0.1:58091/health
```

`/health` 和 `/api/bluetooth/status` 应返回 `ok: true`。

如果 `sink` 为空，通常表示当前没有已连接的 A2DP sink；可在设置页执行连接，或直接调用：

```bash
curl -fsS 'http://127.0.0.1:58091/connect?async=0'
```

连接成功后通常会看到类似：

```text
bluez_sink.44_F7_70_81_9C_C4.a2dp_sink
```

## 回滚

回滚前先确认备份目录，例如：

```text
/volume2/docker/Docker/xiaomiai/backups/v3-redeploy-YYYYMMDD-HHMMSS
```

恢复 compose/config 后重建：

```bash
cd /volume2/docker/Docker/xiaomiai
cp backups/<backup>/docker-compose.yaml ./docker-compose.yaml
cp backups/<backup>/setting.json ./config/setting.json
docker compose up -d --force-recreate xiaomusic
```

## 注意事项

- 不要覆盖已验证的稳定 tag，后续修复应使用新 tag。
- 密码、token、账号 cookie 等敏感信息不要写入文档或提交。
- 蓝牙扫描前必须让目标设备进入可发现/配对模式，建议扫描 60-120 秒。
- sidecar 接管 USB 蓝牙适配器时，宿主机 BlueZ 或旧 host bridge 不应同时抢占同一个 dongle。
