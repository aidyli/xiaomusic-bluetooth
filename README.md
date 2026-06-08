# XiaoMusic: 无限听歌，解放小爱音箱

[![GitHub License](https://img.shields.io/github/license/hanxi/xiaomusic)](https://github.com/hanxi/xiaomusic)
[![Docker Image Version](https://img.shields.io/docker/v/hanxi/xiaomusic?sort=semver&label=docker%20image)](https://hub.docker.com/r/hanxi/xiaomusic)
[![Docker Pulls](https://img.shields.io/docker/pulls/hanxi/xiaomusic)](https://hub.docker.com/r/hanxi/xiaomusic)
[![PyPI - Version](https://img.shields.io/pypi/v/xiaomusic)](https://pypi.org/project/xiaomusic/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/xiaomusic)](https://pypi.org/project/xiaomusic/)
[![Python Version from PEP 621 TOML](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fhanxi%2Fxiaomusic%2Fmain%2Fpyproject.toml)](https://pypi.org/project/xiaomusic/)
[![GitHub Release](https://img.shields.io/github/v/release/hanxi/xiaomusic)](https://github.com/hanxi/xiaomusic/releases)
[![Visitors](https://api.visitorbadge.io/api/daily?path=hanxi%2Fxiaomusic&label=daily%20visitor&countColor=%232ccce4&style=flat)](https://visitorbadge.io/status?path=hanxi%2Fxiaomusic)
[![Visitors](https://api.visitorbadge.io/api/visitors?path=hanxi%2Fxiaomusic&label=total%20visitor&countColor=%232ccce4&style=flat)](https://visitorbadge.io/status?path=hanxi%2Fxiaomusic)

---

<p align="center">
  <strong>🎵 使用小爱音箱播放音乐，音乐使用 yt-dlp 下载</strong>
</p>

<p align="center">
  <a href="https://github.com/hanxi/xiaomusic">🏠 GitHub</a> •
  <a href="https://xdocs.hanxi.cc/">📖 文档</a> •
  <a href="https://github.com/hanxi/xiaomusic/issues/99">💬 FAQ</a> •
  <a href="#-讨论区">💭 讨论区</a>
</p>

---

> [!TIP]
> **新手指南**：初次安装遇到问题请查阅 [💬 FAQ问题集合](https://github.com/hanxi/xiaomusic/issues/99)，一般遇到的问题都已经有解决办法。

## 👋 快速入门指南

已经支持在 web 设置页面配置其他参数，不再需要设置环境变量， docker compose 配置如下（选一个即可）：

```yaml
services:
  xiaomusic:
    image: hanxi/xiaomusic
    container_name: xiaomusic
    restart: always
    ports:
      - 58090:8090
    volumes:
      - /xiaomusic_music:/app/music
      - /xiaomusic_conf:/app/conf
```

🔥 国内：

```yaml
services:
  xiaomusic:
    image: docker.hanxi.cc/hanxi/xiaomusic
    container_name: xiaomusic
    restart: always
    ports:
      - 58090:8090
    volumes:
      - /xiaomusic_music:/app/music
      - /xiaomusic_conf:/app/conf
```

测试版：

```yaml
services:
  xiaomusic:
    image: hanxi/xiaomusic:main
    container_name: xiaomusic
    restart: always
    ports:
      - 58090:8090
    volumes:
      - /xiaomusic_music:/app/music
      - /xiaomusic_conf:/app/conf
```

对应的 docker 启动命令如下:

```bash
docker run -p 58090:8090 -v /xiaomusic_music:/app/music -v /xiaomusic_conf:/app/conf hanxi/xiaomusic
```

🔥 国内：

```bash
docker run -p 58090:8090 -v /xiaomusic_music:/app/music -v /xiaomusic_conf:/app/conf docker.hanxi.cc/hanxi/xiaomusic
```

测试版：

```
docker run -p 58090:8090 -v /xiaomusic_music:/app/music -v /xiaomusic_conf:/app/conf hanxi/xiaomusic:main
```

- 其中 conf 目录为配置文件存放目录，music 目录为音乐存放目录，建议分开配置为不同的目录。
- /xiaomusic_music 和 /xiaomusic_conf 是 docker 所在的主机的目录，可以修改为其他目录。如果报错找不到 /xiaomusic_music 目录，可以先执行 `mkdir -p /xiaomusic_{music,conf}` 命令新建目录。
- /app/music 和 /app/conf 是 docker 容器里的目录，不要去修改。
- 58090 是 NAS 本地端口的。8090 是容器端口，不要去修改。
- 后台访问地址为： http://NAS_IP:58090

> [!NOTE]
> docker 和 docker compose 二选一即可，启动成功后，在 web 页面可以配置其他参数，带有 `*` 号的配置是必须要配置的，其他的用不上时不用修改。初次配置时需要在页面上输入小米账号和密码保存后才能获取到设备列表。

> [!TIP]
> 目前安装步骤已经是最简化了，如果还是嫌安装麻烦，可以微信或者 QQ 约我远程安装，我一般周末和晚上才有时间，需要赞助个辛苦费 :moneybag: 50 元一次。

遇到问题可以去 web 设置页面底部点击【下载日志文件】按钮，然后搜索一下日志文件内容确保里面没有账号密码信息后(有就删除这些敏感信息)，然后在提 issues 反馈问题时把下载的日志文件带上。

> [!TIP]
> 作者新写了一个更简洁的个人音乐服务器，支持更强的插件扩展 <https://github.com/mimusic-org/mimusic>

> [!TIP]
> - 适用于 NAS 上安装的开源工具： <https://github.com/hanxi/tiny-nav>
> - 适用于 NAS 上安装的网页打印机： <https://github.com/hanxi/cups-web>
> - PVE 移动端 UI 界面：<https://github.com/hanxi/pve-touch>
> - 喜欢听书的可以配合这个工具使用 <https://github.com/hanxi/epub2mp3>

> [!TIP]
>
> - 🔥【广告:可用于安装 frp 实现内网穿透】
> - 🔥 海外 RackNerd VPS 机器推荐，可支付宝付款。
> - <a href="https://my.racknerd.com/aff.php?aff=11177"><img src="https://racknerd.com/banners/320x50.gif" alt="RackNerd Mobile Leaderboard Banner" width="320" height="50"></a>
> - 不知道选哪个套餐可以直接买这个最便宜的 <https://my.racknerd.com/aff.php?aff=11177&pid=923>
> - 也可以用来部署代理，docker 部署方法见 <https://github.com/hanxi/blog/issues/96>

> [!TIP]
>
> - 🔥【广告: 搭建您的专属大模型主页
告别繁琐配置难题，一键即可畅享稳定流畅的AI体验！】<https://university.aliyun.com/mobile?userCode=szqvatm6>

> [!TIP]
> - 免费主机
> - <a href="https://dartnode.com?aff=SnappyPigeon570"><img src="https://dartnode.com/branding/DN-Open-Source-sm.png" alt="Powered by DartNode - Free VPS for Open Source" width="320"></a>


## 🎤 功能特性

### 🤐 支持语音口令

#### 基础播放控制
- **播放歌曲** - 播放本地的歌曲
- **播放歌曲+歌名** - 例如：播放歌曲周杰伦晴天
- **上一首** / **下一首** - 切换歌曲
- **关机** / **停止播放** - 停止播放

#### 播放模式
- **单曲循环** - 重复播放当前歌曲
- **全部循环** - 循环播放所有歌曲
- **随机播放** - 随机顺序播放

### 组播放、播放列表选择与蓝牙 sidecar 修复

- 同一 `group_list` 内的多台设备现在会同步播放运行态，包括 `is_playing`、开始时间、时长、暂停偏移和播放 session；任一设备发起新播放时会废弃组内旧 session/timer，避免其他设备的旧进度条或旧下一首定时器影响当前播放。
- 蓝牙 sidecar/立体声组合模式下，任意小爱音箱都只是控制入口，播放输出汇聚到同一个蓝牙组合；任一设备新播放前会全局遍历所有 `XiaoMusicDevice`，取消旧 next/prefetch timer、重置旧进度并废弃旧 session。
- WebSocket/API 在蓝牙组合模式下会统一返回当前播放 owner 的歌曲、歌单、进度和播放状态，避免 A/B 页面各自显示旧任务。
- Web 首页手动选择播放列表时，不再被 WebSocket 推送的“正在播放歌曲所在列表”强制拉回；当前播放信息和进度仍会继续更新。
- Web 设置页支持蓝牙 sidecar 状态刷新、扫描、连接、断开，并对请求追加 cache-buster，避免浏览器/代理缓存导致按钮看似无效。
- 本地部署版本建议通过镜像 tag 和页面部署标识同时识别；当前最终修复镜像 tag 为 `xiaomusic:bluetooth-combo-global-playback-api-owner-20260530-r8`，播放命令应指向 `/host-scripts/call-xiaomi-bt-sidecar.sh {url}`，停止命令应指向 `/host-scripts/stop-xiaomi-bt-sidecar.sh`。

### 蓝牙立体声组合 Sidecar 部署说明

本仓库的蓝牙版本使用“双容器”部署：`xiaomusic` 负责 Web、语音指令和播放任务状态，`bt-audio-sidecar` 独占 USB 蓝牙适配器并负责 BlueZ/PulseAudio/mpv 播放。

```text
XiaoMusic 容器
  -> /host-scripts/call-xiaomi-bt-sidecar.sh {url}
  -> 127.0.0.1:58091 bt-audio-sidecar HTTP bridge
  -> sidecar 内 systemd + D-Bus + bluetooth.service + PulseAudio + mpv
  -> USB 蓝牙 dongle
  -> 蓝牙立体声组合
```

#### 当前生产 Compose 形态

生产部署目录示例：`/volume2/docker/Docker/xiaomiai`。

```yaml
services:
  bt-audio-sidecar:
    image: xiaomusic:bluetooth-sidecar-systemd
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
    image: xiaomusic:bluetooth-combo-global-playback-api-owner-20260530-r8
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
      - /volume1/@home/pleach/Music:/app/music
      - ./config:/app/conf:rw
      - ./cache:/app/cache:rw
```

关键点：

- `bt-audio-sidecar` 必须使用 `privileged: true`，并挂载 `/dev`、`/run/udev`、`/sys`，以便容器内 BlueZ 接管 USB 蓝牙适配器。
- `/sys` 建议只读挂载为 `/sys:/sys:ro`；生产验证中，读写挂载曾导致 BlueZ adapter/GATT 初始化异常。
- `/var/lib/bluetooth` 持久化到 `./bt-sidecar-systemd/state/bluetooth`，避免每次重建容器都重新配对。
- 两个容器都使用 `network_mode: host`，所以 XiaoMusic 容器内访问 `127.0.0.1:58091` 就是访问 sidecar bridge。

#### `xiaomusic:bluetooth-sidecar-systemd` 镜像来源

`xiaomusic:bluetooth-sidecar-systemd` 是本地构建的 Debian systemd 蓝牙 sidecar 镜像，不是上游官方镜像。它的职责是：

- 运行 systemd、D-Bus 和 `bluetooth.service`；
- 运行 PulseAudio system daemon，并加载 Bluetooth A2DP 相关模块；
- 运行一个 Python HTTP bridge，提供 `/health`、`/status`、`/scan`、`/connect`、`/play`、`/stop`、`/disconnect`；
- 调用 `mpv` 把 XiaoMusic 传入的音频 URL 播放到 BlueZ A2DP sink。

镜像构建目录建议放在部署目录旁，例如：

```text
/volume2/docker/Docker/xiaomiai/bt-sidecar-systemd/
```

构建目录至少包含：

```text
Dockerfile
sidecar-server.py
pulse-system.pa
bt-prep.service
bt-pulseaudio.service
bt-sidecar-bridge.service
```

Dockerfile 核心内容：

```dockerfile
FROM debian:bookworm-slim
ENV container=docker DEBIAN_FRONTEND=noninteractive
STOPSIGNAL SIGRTMIN+3
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    systemd systemd-sysv dbus bluez bluez-tools rfkill usbutils procps psmisc \
    pulseaudio pulseaudio-module-bluetooth pulseaudio-utils \
    mpv ffmpeg ca-certificates python3 curl kmod \
 && rm -rf /var/lib/apt/lists/* \
 && systemctl set-default multi-user.target \
 && systemctl enable bluetooth.service
COPY sidecar-server.py /usr/local/bin/sidecar-server.py
COPY pulse-system.pa /etc/pulse/system.pa
COPY bt-pulseaudio.service /etc/systemd/system/bt-pulseaudio.service
COPY bt-sidecar-bridge.service /etc/systemd/system/bt-sidecar-bridge.service
COPY bt-prep.service /etc/systemd/system/bt-prep.service
RUN chmod +x /usr/local/bin/sidecar-server.py \
 && systemctl enable bt-prep.service bt-pulseaudio.service bt-sidecar-bridge.service
CMD ["/sbin/init"]
```

构建命令：

```bash
cd /volume2/docker/Docker/xiaomiai/bt-sidecar-systemd
docker build -t xiaomusic:bluetooth-sidecar-systemd .
```

如果需要离线迁移到另一台机器，可以打包镜像：

```bash
docker save xiaomusic:bluetooth-sidecar-systemd | gzip > xiaomusic-bluetooth-sidecar-systemd.tar.gz
sha256sum xiaomusic-bluetooth-sidecar-systemd.tar.gz
```

在目标机器导入：

```bash
gunzip -c xiaomusic-bluetooth-sidecar-systemd.tar.gz | docker load
```

#### 主 XiaoMusic 蓝牙版镜像来源

主应用镜像 `xiaomusic:bluetooth-combo-global-playback-api-owner-20260530-r8` 来自本仓库蓝牙分支/提交构建，用于区分部署版本。推荐从仓库根目录构建：

```bash
cd /path/to/xiaomusic
docker build -t xiaomusic:bluetooth-combo-global-playback-api-owner-20260530-r8 .
```

也可以打包迁移：

```bash
docker save xiaomusic:bluetooth-combo-global-playback-api-owner-20260530-r8 | gzip > xiaomusic-bluetooth-combo-global-playback-api-owner-20260530-r8.tar.gz
sha256sum xiaomusic-bluetooth-combo-global-playback-api-owner-20260530-r8.tar.gz
```

#### Sidecar HTTP 接口

默认监听：`127.0.0.1:58091`。

```text
GET /health
GET /status
GET /scan?seconds=90
GET /connect?async=0
GET /play?url=<encoded-url>
GET /stop
GET /disconnect
```

常用验证：

```bash
curl -fsS http://127.0.0.1:58091/health
curl -fsS http://127.0.0.1:58091/status
curl -fsS 'http://127.0.0.1:58090/api/bluetooth/status?_=verify'
docker exec xiaomusic /host-scripts/call-xiaomi-bt-sidecar.sh 'av://lavfi:sine=frequency=880:duration=5'
docker exec xiaomusic /host-scripts/stop-xiaomi-bt-sidecar.sh
```

#### 蓝牙扫描与配对注意事项

- 扫描前先让“立体声组合”进入可发现/配对模式。
- 扫描建议 60-120 秒，短扫描可能错过设备窗口。
- 如果重建 sidecar 后无法连接，优先检查 `/var/lib/bluetooth` 持久化状态、目标 MAC、`/health` 是否有 `bluez_sink`。
- 当前 sidecar 接管 USB 蓝牙 dongle 时，宿主机上的 BlueZ/旧 bridge 不应同时接管同一个适配器。

#### 歌单管理
- **播放歌单+目录名** - 例如：播放歌单其他
- **播放歌单第几个+列表名** - 详见 [#158](https://github.com/hanxi/xiaomusic/issues/158)
- **播放歌单收藏** - 播放收藏歌单

#### 收藏功能
- **加入收藏** - 将当前播放的歌曲加入收藏歌单
- **取消收藏** - 将当前播放的歌曲从收藏歌单移除

> [!TIP]
> **隐藏玩法**：对小爱同学说"播放歌曲小猪佩奇的故事"，会先下载小猪佩奇的故事，然后再播放。

## 📦 安装方式

### 方式一：Docker Compose（推荐）

详见 [👋 快速入门指南](#-快速入门指南)

### 方式二：Pip 安装

```shell
# 安装
pip install -U xiaomusic

# 查看帮助
xiaomusic --help

# 启动（使用配置文件）
xiaomusic --config config.json

# 启动（使用默认端口 8090）
xiaomusic
```

> [!NOTE]
> `config.json` 文件可以参考 `config-example.json` 文件配置。详见 [#94](https://github.com/hanxi/xiaomusic/issues/94)

## 👨‍💻 开发指南

### 🔩 开发环境运行

1. **下载依赖**
   ```shell
   ./install_dependencies.sh
   ```

2. **安装环境**
   ```shell
   pdm install
   ```

3. **启动服务**
   ```shell
   pdm run xiaomusic.py
   ```
   默认监听端口 8090，使用其他端口请自行修改。

4. **查看 API 文档**
   
   访问 <http://localhost:8090/docs> 查看接口文档。

> [!NOTE]
> 目前的 web 控制台非常简陋，欢迎有兴趣的朋友帮忙实现一个漂亮的前端，需要什么接口可以随时提需求。

### 🚦 代码提交规范

提交前请执行以下命令检查代码和格式化代码：

```shell
pdm lintfmt
```

### 🐳 本地编译 Docker Image

```shell
docker build -t xiaomusic .
```

### 🛠️ 技术栈

- **后端**：Python + FastAPI 框架
- **容器化**：Docker
- **前端**：jQuery

## 📱 设备支持

### 已测试支持的设备

| 型号 | 设备名称 |
|------|---------|
| **L06A** | [小爱音箱](https://home.mi.com/baike/index.html#/detail?model=xiaomi.wifispeaker.l06a) |
| **L07A** | [Redmi小爱音箱 Play](https://home.mi.com/webapp/content/baike/product/index.html?model=xiaomi.wifispeaker.l7a) |
| **S12/S12A/MDZ-25-DA** | [小米AI音箱](https://home.mi.com/baike/index.html#/detail?model=xiaomi.wifispeaker.s12) |
| **LX5A** | [小爱音箱 万能遥控版](https://home.mi.com/baike/index.html#/detail?model=xiaomi.wifispeaker.lx5a) |
| **LX05** | [小爱音箱Play（2019款）](https://home.mi.com/baike/index.html#/detail?model=xiaomi.wifispeaker.lx05) |
| **L15A** | [小米AI音箱（第二代）](https://home.mi.com/webapp/content/baike/product/index.html?model=xiaomi.wifispeaker.l15a#/) |
| **L16A** | [Xiaomi Sound](https://home.mi.com/baike/index.html#/detail?model=xiaomi.wifispeaker.l16a) |
| **L17A** | [Xiaomi Sound Pro](https://home.mi.com/baike/index.html#/detail?model=xiaomi.wifispeaker.l17a) |
| **LX06** | [小爱音箱Pro](https://home.mi.com/baike/index.html#/detail?model=xiaomi.wifispeaker.lx06) |
| **LX01** | [小爱音箱mini](https://home.mi.com/baike/index.html#/detail?model=xiaomi.wifispeaker.lx01) |
| **L05B** | [小爱音箱Play](https://home.mi.com/baike/index.html#/detail?model=xiaomi.wifispeaker.l05b) |
| **L05C** | [小米小爱音箱Play 增强版](https://home.mi.com/baike/index.html#/detail?model=xiaomi.wifispeaker.l05c) |
| **L09A** | [小米音箱Art](https://home.mi.com/webapp/content/baike/product/index.html?model=xiaomi.wifispeaker.l09a) |
| **LX04/X10A/X08A** | 触屏版音箱 |
| **X08C/X08E/X8F** | 触屏版音箱 |
| **M01/XMYX01JY** | 小米小爱音箱HD |
| **OH2P** | XIAOMI 智能音箱 Pro |
| **OH2** | XIAOMI 智能音箱 |

> [!NOTE]
> - 型号与产品名称对照可在 [小米IoT平台](https://home.miot-spec.com/s/xiaomi.wifispeaker) 查询
> - 如果你的设备支持播放，请反馈给我添加到支持列表里，谢谢
> - 目前应该所有设备类型都已经支持播放，有问题可随时反馈

### 🎵 支持音乐格式

- **mp3** - 标准音频格式
- **flac** - 无损音频格式
- **wav** - 无损音频格式
- **ape** - 无损音频格式
- **ogg** - 开源音频格式
- **m4a** - AAC 音频格式

> [!NOTE]
> - 本地音乐会搜索目录下上面格式的文件，下载的歌曲是 mp3 格式
> - 已知 L05B、L05C、LX06、L16A 不支持 flac 格式
> - 如果格式不能播放可以打开【转换为MP3】和【型号兼容模式】选项，详见 [#153](https://github.com/hanxi/xiaomusic/issues/153#issuecomment-2328168689)

## 🌏 网络歌单功能

可以配置一个 json 格式的歌单，支持电台和歌曲，也可以直接用别人分享的链接。同时配备了 m3u 文件格式转换工具，可以很方便地把 m3u 电台文件转换成网络歌单格式的 json 文件。

详细用法见 [#78](https://github.com/hanxi/xiaomusic/issues/78)

> [!NOTE]
> 欢迎有想法的朋友们制作更多的歌单转换工具，一起完善项目功能！

## ⚠️ 安全提醒

> [!IMPORTANT]
>
> 1. 如果配置了公网访问 xiaomusic ，请一定要开启密码登陆，并设置复杂的密码。且不要在公共场所的 WiFi 环境下使用，否则可能造成小米账号密码泄露。
> 2. 强烈不建议将小爱音箱的小米账号绑定摄像头，代码难免会有 bug ，一旦小米账号密码泄露，可能监控录像也会泄露。

## 💬 社区与支持

### 📢 讨论区

<p align="center">
  <a href="https://github.com/hanxi/xiaomusic/issues">💬 GitHub Issues</a> •
  <a href="https://pd.qq.com/s/e2jybz0ss">🎮 QQ频道</a> •
  <a href="https://qm.qq.com/q/vQtFRinceA">👥 QQ交流群</a> •
  <a href="https://github.com/hanxi/xiaomusic/issues/86">💬 微信群</a>
</p>

### 🤝 如何贡献

我们欢迎所有形式的贡献，包括但不限于：

- 🐛 **报告 Bug**：在 [Issues](https://github.com/hanxi/xiaomusic/issues) 中提交问题
- 💡 **功能建议**：分享你的想法和建议
- 📝 **改进文档**：帮助完善文档和教程
- 🎨 **前端美化**：优化 Web 控制台界面
- 🔧 **代码贡献**：提交 Pull Request

> [!TIP]
> 提交代码前请确保运行 `pdm lintfmt` 检查代码规范

## 📚 相关资源

### 👉 更多教程

更多功能见 [📝 文档汇总](https://github.com/hanxi/xiaomusic/issues/211)

### 🎨 第三方主题

- [pure 主题 xiaomusicUI](https://github.com/52fisher/xiaomusicUI)
- [移动端的播放器主题](https://github.com/52fisher/XMusicPlayer)
- [Tailwind主题](https://github.com/clarencejh/xiaomusic)
- [SoundScape主题](https://github.com/jhao0413/SoundScape)
- [第三方主题](https://github.com/DarrenWen/xiaomusicui)

### 📱 配套应用

- [微信小程序: 卯卯音乐](https://github.com/F-loat/xiaoplayer)
- [手机APP: 风花雪乐](https://github.com/jokezc/mi_music)
- [JS在线播放插件](https://github.com/boluofan/xiaomusic-online)
- [手机APP: HMusic](https://github.com/hpcll/HMusic)
- [安卓TV: 肉肉音乐TV](https://github.com/GanHuaLin/rouroumusic-tv)

### ❤️ 致谢

**核心依赖**
- [xiaomi](https://www.mi.com/) - 小米智能设备
- [xiaogpt](https://github.com/yihong0618/xiaogpt) - 项目灵感来源
- [MiService](https://github.com/yihong0618/MiService) - 小米服务接口
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - 音乐下载工具

**开发工具**
- [PDM](https://pdm.fming.dev/latest/) - Python 包管理
- [FastAPI](https://fastapi.tiangolo.com/) - Web 框架
- [Umami](https://github.com/umami-software/umami) - 统计分析
- [Sentry](https://github.com/getsentry/sentry) - 报错监控

**参考资料**
- [实现原理](https://github.com/yihong0618/gitblog/issues/258)
- [awesome-xiaoai](https://github.com/zzz6519003/awesome-xiaoai)

**特别感谢**
- 所有帮忙调试和测试的朋友
- 所有反馈问题和建议的朋友
- 所有贡献代码和文档的开发者

## 🚨 免责声明

本项目仅供学习和研究目的，不得用于任何商业活动。用户在使用本项目时应遵守所在地区的法律法规，对于违法使用所导致的后果，本项目及作者不承担任何责任。
本项目可能存在未知的缺陷和风险（包括但不限于设备损坏和账号封禁等），使用者应自行承担使用本项目所产生的所有风险及责任。
作者不保证本项目的准确性、完整性、及时性、可靠性，也不承担任何因使用本项目而产生的任何损失或损害责任。
使用本项目即表示您已阅读并同意本免责声明的全部内容。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=hanxi/xiaomusic&type=Date)](https://star-history.com/#hanxi/xiaomusic&Date)

## 💖 支持项目

如果这个项目对你有帮助，欢迎通过以下方式支持：

### ⭐ Star 项目
点击右上角的 ⭐ Star 按钮，让更多人发现这个项目

### 💰 赞赏支持
- [💝 爱发电](https://afdian.com/a/imhanxi) - 持续支持项目发展
- 扫码请作者喝杯奶茶 ☕

<p align="center">
  <img src="https://i.v2ex.co/7Q03axO5l.png" alt="赞赏码" width="300">
</p>

### 🎁 其他支持方式
- 分享给更多需要的朋友
- 提交 Bug 报告和功能建议
- 贡献代码和文档

---

<p align="center">
  <strong>感谢你的支持！❤️</strong>
</p>

## License

[MIT](https://github.com/hanxi/xiaomusic/blob/main/LICENSE) License © 2024 涵曦
