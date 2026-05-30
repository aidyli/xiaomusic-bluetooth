"""设备播放控制模块

负责单个设备的播放控制、下载管理、TTS处理等功能。
"""

import asyncio
import copy
import hashlib
import json
import os
import random
import shlex
import shutil
import time
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp
from miservice import miio_command

from xiaomusic.config import Device

if TYPE_CHECKING:
    from xiaomusic.xiaomusic import XiaoMusic
from xiaomusic.const import (
    NEED_USE_PLAY_MUSIC_API,
    PLAY_TYPE_ALL,
    PLAY_TYPE_ONE,
    PLAY_TYPE_RND,
    PLAY_TYPE_SEQ,
    PLAY_TYPE_SIN,
    TTS_COMMAND,
)
from xiaomusic.events import DEVICE_CONFIG_CHANGED
from xiaomusic.utils.file_utils import chmodfile
from xiaomusic.utils.system_utils import try_add_access_control_param
from xiaomusic.utils.text_utils import (
    custom_sort_key,
    list2str,
    parse_ordinal_suffix,
)


class XiaoMusicDevice:
    """设备播放控制类

    负责单个小爱设备的播放控制，包括：
    - 播放控制（播放、暂停、上一首、下一首）
    - 播放列表管理
    - 下载管理
    - TTS（文字转语音）
    - 定时器管理
    - 设备状态管理
    """

    def __init__(self, xiaomusic: "XiaoMusic", device: Device, group_name: str):
        """初始化设备播放控制器

        Args:
            xiaomusic: XiaoMusic 主类实例
            device: 设备配置对象
            group_name: 设备组名
        """
        self.group_name = group_name
        self.device = device
        self.config = xiaomusic.config
        self.device_id = device.device_id
        self.log = xiaomusic.log
        self.xiaomusic = xiaomusic
        self.auth_manager = xiaomusic.auth_manager
        self.ffmpeg_location = self.config.ffmpeg_location
        self.event_bus = getattr(xiaomusic, "event_bus", None)

        self._download_proc = None  # 下载对象
        self._next_timer = None
        self.is_playing = False
        # 播放进度
        self._start_time = 0
        self._duration = 0
        self._paused_time = 0
        self._play_failed_cnt = 0

        self._play_list = []

        # 关机定时器
        self._stop_timer = None
        self._last_cmd = None
        self._pending_selection = None
        self._pending_selection_count = 0
        self.update_playlist()

        # 添加歌曲定时器
        self._add_song_timer = None
        # TTS 播放定时器
        self._tts_timer = None
        # 用于预缓存下一首的定时器
        self._prefetch_timer = None
        # 播放会话代际。每次主动播放/抢占都会递增，旧的下一首/预缓存任务触发时必须先校验。
        self._play_session_id = 0
        # 方案 C：播放前 stop -> 预热 -> 并发下发，stop 与预热之间保留极短缓冲。
        self._stereo_split_stop_settle_sec = 0.12

    @property
    def did(self):
        """获取设备DID"""
        return self.device.did

    @property
    def hardware(self):
        """获取设备硬件型号"""
        return self.device.hardware

    def get_cur_music(self):
        """获取当前播放的音乐名称"""
        return self.device.cur_music

    def get_offset_duration(self):
        """获取播放偏移量和总时长"""
        duration = self._duration
        if not self.is_playing:
            return 0, duration
        offset = time.time() - self._start_time - self._paused_time
        return offset, duration

    # 自动搜歌并加入当前歌单
    async def auto_add_song(self, cur_list_name, sleep_sec=20):
        if self.xiaomusic.js_plugin_manager is None:
            return
        # 是否启用自动添加
        auto_add_song = self.xiaomusic.js_plugin_manager.get_auto_add_song()
        is_online = self.xiaomusic.music_library.is_online_music(cur_list_name)
        # 采用作者建议的黑名单模式，直接排除以 "_online_iwp_" 开头的自定义歌单
        is_allowed_list = is_online and not cur_list_name.startswith("_online_iwp_")
        # 歌单循环方式：播放全部
        play_all = self.device.play_type == PLAY_TYPE_ALL
        # 当前播放的歌曲是歌单中的最后一曲
        is_last_song = False
        cur_playlist = self._play_list
        cur_music = self.get_cur_music()
        play_list_len = len(cur_playlist)
        if play_list_len != 0:
            index = self._play_list.index(cur_music)
            is_last_song = index == play_list_len - 1
        # 四个条件都满足，才自动添加下一首
        if auto_add_song and is_allowed_list and play_all and is_last_song:
            await self._add_singer_song(cur_list_name, cur_music, sleep_sec)

    # 启用延时器，搜索当前歌曲歌手的其他不在歌单内的歌曲
    async def _add_singer_song(self, list_name, cur_music, sleep_sec):
        # 取消之前的定时器（如果存在）
        # self.cancel_add_song_timer()
        # 以 '-' 分割，获取歌手名称
        singer_name = cur_music.split("-")[1]
        # 创建新的定时器，20秒后执行
        self._add_song_timer = asyncio.create_task(
            self._delayed_add_singer_song(list_name, singer_name, sleep_sec)
        )

    async def _delayed_add_singer_song(self, list_name, singer_name, sleep_sec):
        """延迟执行添加歌手歌曲的操作"""
        try:
            await asyncio.sleep(sleep_sec)
            await self.xiaomusic.add_singer_song(list_name, singer_name)
        except asyncio.CancelledError:
            return
        finally:
            # 执行完毕后清除定时器引用
            if self._add_song_timer:  # 确保是当前任务
                self._add_song_timer = None

    def cancel_add_song_timer(self):
        """取消添加歌曲的定时器"""
        self.log.info("添加歌手歌曲的定时器已被取消")
        if self._add_song_timer:
            self._add_song_timer.cancel()
            self._add_song_timer = None
            return True
        return False

    async def play_music(self, name):
        """播放音乐（外部接口）"""
        return await self._playmusic(name)

    def update_playlist(self, force_reshuffle=False):
        """
        初始化或更新播放列表。

        【核心架构特点】：
        1. 状态保持 (Stateful Shuffle)：随机模式下，生成一次乱序列表后永久保持，避免反复洗牌导致预缓存断链和歌曲无限循环。
        2. 洗牌置顶 (Pin-to-Top)：当发生全量重洗时，将当前正在播放的歌曲强行“钉”在列表最顶端(index 0)，完美闭环预缓存机制。
        3. 增量更新 (Incremental Update)：歌单发生变化（如自动追加了歌手新歌）时，不打乱原有播放顺序，仅将新歌洗牌后追加到队尾。

        Args:
            force_reshuffle (bool): 是否强制彻底重新洗牌（用于切换模式、切换歌单、或一轮播放触底时）
        """
        # 1. 兜底保护：如果没有重置 list 且当前歌单在系统里不存在，默认切到"全部"
        if self.device.cur_playlist not in self.xiaomusic.music_library.music_list:
            self.device.cur_playlist = "全部"

        list_name = self.device.cur_playlist
        # 获取大管家（Library）里最新鲜的歌单数据
        latest_list = self.xiaomusic.music_library.music_list[list_name]

        # ==========================================
        # 随机播放模式 (PLAY_TYPE_RND) 的调度
        # ==========================================
        if self.device.play_type == PLAY_TYPE_RND:
            # 判断是否需要【全量重洗牌】的三个条件：
            # A. 外部明确要求强洗 (force_reshuffle=True)
            # B. 当前播放列表是空的 (系统刚启动)
            # C. 当前播放列表和最新的歌单毫无交集 (说明用户切了全新的歌单)
            if (
                force_reshuffle
                or not self._play_list
                or not set(self._play_list).intersection(set(latest_list))
            ):
                self._play_list = copy.copy(latest_list)
                random.shuffle(self._play_list)

                # 2：洗牌置顶 (Pin-to-Top)
                # 防止洗牌后当前歌曲位置丢失，导致下一首乱跳和预缓存错位
                cur_music = self.get_cur_music()
                if cur_music and cur_music in self._play_list:
                    self._play_list.remove(cur_music)
                    self._play_list.insert(0, cur_music)

                self.log.info(f"彻底重新洗牌 {list_name}，并将当前歌曲置顶")

            # 【增量更新牌库】
            else:
                # 3：增量更新 (Incremental Update)
                old_list = self._play_list
                latest_set = set(latest_list)
                old_set = set(old_list)

                # A. 剔除云端已经被删除的歌，保留依然存在的歌（绝对不改变它们的相对顺序！）
                self._play_list = [s for s in old_list if s in latest_set]

                # B. 找出最新歌单里多出来的新歌（比如 auto_add_song 追加进来的）
                new_songs = [s for s in latest_list if s not in old_set]
                if new_songs:
                    # 把新来的歌单独洗乱，然后悄悄垫在牌堆的最底下
                    random.shuffle(new_songs)
                    self._play_list.extend(new_songs)
                    self.log.info(
                        f"歌单有更新，保持原顺序并追加了 {len(new_songs)} 首新歌"
                    )

        # ==========================================
        # 顺序/循环模式的处理
        # ==========================================
        else:
            self._play_list = copy.copy(latest_list)
            is_online = self.xiaomusic.music_library.is_online_music(list_name)

            # 如果是本地目录歌单，且列表都是纯字符串，执行本地特定的字母自然排序
            if not is_online and len(self._play_list) > 0:
                has_non_str_item = any(
                    not isinstance(item, str) for item in self._play_list
                )
                if not has_non_str_item:
                    self._play_list.sort(key=custom_sort_key)
            self.log.info(f"顺序模式更新，不打乱 {list_name}")

    async def play(self, name="", search_key=""):
        """播放歌曲（外部接口）"""
        self._last_cmd = "play"
        return await self._play(name=name, search_key=search_key)

    async def _check_and_download_music(self, name, search_key, allow_download):
        """检查本地歌曲是否存在，如果不存在则根据参数决定是否下载

        Args:
            name: 歌曲名称
            search_key: 搜索关键词
            allow_download: 是否允许下载

        Returns:
            bool: True表示歌曲存在或下载成功，False表示歌曲不存在且不允许下载
        """
        if self.xiaomusic.music_library.is_music_exist(name):
            return True

        self.log.info(f"本地不存在歌曲{name}")

        # 根据 allow_download 参数决定行为
        if not allow_download:
            # playlocal 的行为：不下载，直接提示
            await self.do_tts(f"本地不存在歌曲{name}")
            return False

        # _play 的行为：检查配置决定是否下载
        if self.config.disable_download:
            await self.do_tts(f"本地不存在歌曲{name}")
            return False

        # 下载歌曲
        await self.download(search_key, name)
        # 把文件插入到播放列表里
        await self.add_download_music(name)
        return True

    async def _play_internal(self, name="", search_key="", allow_download=True):
        """播放歌曲的内部统一实现

        Args:
            name: 歌曲名称
            search_key: 搜索关键词
            allow_download: 是否允许下载（True: _play行为，False: playlocal行为）
        """
        # 清除旧的待选择状态
        if self._pending_selection:
            self.log.info(f"清除旧的待选择状态，重新搜索: {name}")
            self._pending_selection = None
            self._pending_selection_count = 0

        # 初始检查逻辑
        self._apply_group_state_to_device()
        if not search_key and not name:
            if self.check_play_next():
                await self._play_next()
                return
            else:
                name = self.get_cur_music()

        self.log.info(
            f"play_internal. search_key:{search_key} name:{name} allow_download:{allow_download}"
        )

        if not name:
            self.log.info(f"没有歌曲播放了 name:{name} search_key:{search_key}")
            return

        max_results = self.config.fuzzy_match_max_results
        auto_index = None

        parsed_name, parsed_index = parse_ordinal_suffix(name)
        if parsed_index is not None:
            full_names = self.xiaomusic.music_library.find_real_music_name(
                name, n=max_results
            )
            if full_names:
                self.log.info(
                    f"完整名称'{name}'有{len(full_names)}条匹配，优先使用完整名称搜索"
                )
                names = full_names
            else:
                self.log.info(
                    f"完整名称'{name}'无匹配，使用'{parsed_name}'搜索并自动选择第{parsed_index}个"
                )
                name = parsed_name
                search_key = parsed_name
                auto_index = parsed_index
                names = self.xiaomusic.music_library.find_real_music_name(
                    name, n=max_results
                )
        else:
            names = self.xiaomusic.music_library.find_real_music_name(
                name, n=max_results
            )

        self.log.info(
            f"play_internal. 搜索关键词:{name} 匹配数量:{len(names)} auto_index:{auto_index}"
        )
        if len(names) > 1:
            for idx, music_name in enumerate(names, 1):
                self.log.info(f"  第{idx}个: {music_name}")

        if len(names) > 1:
            if auto_index is not None and 1 <= auto_index <= len(names):
                self._pending_selection = names
                self._pending_selection_count = len(names)
                self._sync_group_state_to_devices()
                self.log.info(f"自动选择第{auto_index}个: {names[auto_index - 1]}")
                await self.handle_selection(auto_index)
                return

            if not self.config.enable_multi_result_selection:
                action = self.config.multi_result_action
                if action == "first":
                    selected_index = 1
                else:
                    selected_index = random.randint(1, len(names))
                selected_name = names[selected_index - 1]
                self.log.info(
                    f"多结果选择已关闭，按'{action}'处理，选择第{selected_index}个: {selected_name}"
                )
                self._pending_selection = names
                self._pending_selection_count = len(names)
                self._sync_group_state_to_devices()
                await self._playmusic(selected_name)
                return

            self._pending_selection = names
            self._pending_selection_count = len(names)
            self._sync_group_state_to_devices()
            selection_text = (
                f"共找到{len(names)}条匹配记录，请重新呼叫小爱同学并告诉她第几个"
            )
            self.log.info(selection_text)
            await self.xiaomusic.do_tts(self.did, selection_text)
            return

        if not names:
            # 检查本地是否存在歌曲，不存在则根据参数决定是否下载
            if not await self._check_and_download_music(
                name, search_key, allow_download
            ):
                return

            # 播放歌曲
            await self._playmusic(name)
            return

        name = names[0]
        if name not in self._play_list:
            # 根据当前歌曲匹配歌曲列表
            self.device.cur_playlist = self.find_cur_playlist(name)
            self.update_playlist()

        self.log.debug(
            f"当前播放列表为：{list2str(self._play_list, self.config.verbose)}"
        )
        # 本地存在歌曲，直接播放
        await self._playmusic(name)

    async def _play(self, name="", search_key=""):
        """播放歌曲（内部实现）- 支持下载"""
        return await self._play_internal(
            name=name,
            search_key=search_key,
            allow_download=True,
        )

    async def play_next(self):
        """播放下一首（外部接口）"""
        return await self._play_next()

    async def _play_next(self):
        """播放下一首（内部实现）"""
        self._apply_group_state_to_device()
        self.log.info("开始播放下一首")
        name = self.get_cur_music()
        if (
            self.device.play_type == PLAY_TYPE_ALL
            or self.device.play_type == PLAY_TYPE_RND
            or self.device.play_type == PLAY_TYPE_SEQ
            or name == ""
            or (
                (name not in self._play_list) and self.device.play_type != PLAY_TYPE_ONE
            )
        ):
            name = self.get_next_music()
            self.log.info(f"get_next_music {name}")
        self.log.info(f"_play_next. name:{name}, cur_music:{self.get_cur_music()}")
        if name == "":
            self.log.info("本地没有歌曲")
            return
        await self._play(name)

    async def play_prev(self):
        """播放上一首（外部接口）"""
        return await self._play_prev()

    async def _play_prev(self):
        """播放上一首（内部实现）"""
        self._apply_group_state_to_device()
        self.log.info("开始播放上一首")
        name = self.get_cur_music()
        if (
            self.device.play_type == PLAY_TYPE_ALL
            or self.device.play_type == PLAY_TYPE_RND
            or self.device.play_type == PLAY_TYPE_SEQ
            or name == ""
            or (name not in self._play_list)
        ):
            name = self.get_prev_music()
        self.log.info(f"_play_prev. name:{name}, cur_music:{self.get_cur_music()}")
        if name == "":
            await self.do_tts("本地没有歌曲")
            return
        await self._play(name)

    async def playlocal(self, name=""):
        """播放本地歌曲 - 不下载"""
        self._last_cmd = "playlocal"
        return await self._play_internal(name=name, search_key="", allow_download=False)

    async def prefetch_next_song(self, sleep_sec, session_id=None):
        """延时后台预加载（缓存）下一首歌曲"""
        if self._prefetch_timer:
            self._prefetch_timer.cancel()
        if session_id is None:
            session_id = self._play_session_id

        async def _do_prefetch():
            try:
                await asyncio.sleep(sleep_sec)
                if not self._is_current_session(session_id):
                    self.log.info(
                        f"预缓存任务已过期，跳过 did:{self.did} session:{session_id} current:{self._play_session_id}"
                    )
                    return

                # 拿下一首歌的名字
                next_music = self.get_next_music()
                if not next_music:
                    return

                # 如果是网络音乐，触发预下载
                if self.xiaomusic.music_library.is_web_music(next_music):
                    self.log.info(f"开始后台预先缓存下一首: {next_music}")
                    cur_playlist = self.device.cur_playlist
                    # 巧妙利用我们重构过的时长函数，底层会自动走：没缓存 -> 去下载 -> 存硬盘 的闭环
                    await self.xiaomusic.music_library.get_music_duration(
                        next_music, cur_playlist
                    )
                    self.log.info(f"后台预先缓存完成: {next_music}")

                await self.prefetch_stereo_split_for_music(next_music)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self.log.error(f"预加载下一首歌曲失败: {e}")

        self._prefetch_timer = asyncio.create_task(_do_prefetch())
        self.log.info(f"{sleep_sec} 秒后预缓存下一首歌曲 did:{self.did} session:{session_id}")

    async def _cancel_prefetch_timer(self):
        """取消预缓存下一首任务。"""
        if not self._prefetch_timer:
            return
        self._prefetch_timer.cancel()
        try:
            await self._prefetch_timer
        except asyncio.CancelledError:
            pass
        self._prefetch_timer = None
        self.log.info(f"预缓存定时器已取消 did: {self.did}")

    def _bump_play_session(self):
        """递增本设备播放会话代际，使旧异步任务失效。"""
        self._play_session_id += 1
        return self._play_session_id

    def _get_group_play_state(self):
        """获取同组共享播放状态；没有 device_manager 时退化为本设备状态。"""
        device_manager = self.xiaomusic.device_manager
        if device_manager is None:
            if not hasattr(self, "_local_group_play_state"):
                self._local_group_play_state = {}
            return self._local_group_play_state
        return device_manager.get_group_play_state(self.group_name)

    def _sync_group_state_from_device(self):
        """把当前设备播放任务快照同步到同组共享状态。"""
        state = self._get_group_play_state()
        state.update(
            {
                "cur_playlist": self.device.cur_playlist,
                "cur_music": self.get_cur_music(),
                "play_type": self.device.play_type,
                "play_list": copy.copy(self._play_list),
                "pending_selection": copy.copy(self._pending_selection),
                "pending_selection_count": self._pending_selection_count,
            }
        )
        return state

    def _apply_group_state_to_device(self):
        """在处理语音命令前吸收同组共享状态，确保任一音箱入口都接着同一任务操作。"""
        state = self._get_group_play_state()
        if not state:
            return state
        cur_playlist = state.get("cur_playlist")
        cur_music = state.get("cur_music")
        play_type = state.get("play_type")
        play_list = state.get("play_list")
        pending_selection = state.get("pending_selection")
        pending_selection_count = state.get("pending_selection_count")
        if cur_playlist:
            self.device.cur_playlist = cur_playlist
        if play_type:
            self.device.play_type = play_type
        if cur_music:
            self.device.playlist2music[self.device.cur_playlist] = cur_music
        if isinstance(play_list, list):
            self._play_list = copy.copy(play_list)
        if isinstance(pending_selection, list):
            self._pending_selection = copy.copy(pending_selection)
            self._pending_selection_count = pending_selection_count or len(pending_selection)
        return state

    def _sync_group_state_to_devices(self):
        """把共享任务写回组内所有设备，保持 UI、下一首、任意语音入口一致。"""
        state = self._sync_group_state_from_device()
        device_manager = self.xiaomusic.device_manager
        if device_manager is None:
            return state
        for device in device_manager.get_group_devices(self.group_name).values():
            if device is self:
                continue
            device._apply_group_state_to_device()
        return state

    async def _invalidate_group_play_sessions(self):
        """让组内旧播放会话失效，并取消所有旧的下一首/预缓存任务。

        在 group_list/stereo_split 场景下，任意一只音箱的新播放请求都会接管整组。
        如果只取消当前 did 的定时器，另一只音箱旧歌曲的 next timer 仍会在到点后
        调用 _play_next()，从而打断当前正在播放的新歌曲。
        """
        device_manager = self.xiaomusic.device_manager
        if device_manager is None:
            self._bump_play_session()
            await self.cancel_next_timer()
            await self._cancel_prefetch_timer()
            return self._play_session_id
        devices = device_manager.get_group_devices(self.group_name)
        self.log.info(f"invalidate_group_play_sessions {self.group_name} {list(devices.keys())}")
        for device in devices.values():
            device._bump_play_session()
            await device.cancel_next_timer()
            await device._cancel_prefetch_timer()
        # 返回当前设备的新 session，供本次播放设置 timer 时绑定。
        return self._play_session_id

    def _is_current_session(self, session_id):
        return session_id == self._play_session_id

    async def _playmusic(self, name):
        """播放音乐的核心实现"""
        # 新的主动播放请求接管整组：取消 A/B 两边旧的 next/prefetch 任务，
        # 并递增会话代际，防止旧歌曲结束后的 _play_next 抢占当前播放。
        self._apply_group_state_to_device()
        session_id = await self._invalidate_group_play_sessions()

        # 先确认该歌单下能解析出播放 URL；确认成功后再更新当前播放状态，避免 UI/WebSocket
        # 在死链、探路失败、设备下发失败时短暂显示成“下一首”但实际仍停在上一首。
        cur_playlist = self.device.cur_playlist
        url, _ = await self.xiaomusic.music_library.get_music_url(name, cur_playlist)

        # 1. 命中硬盘级负向缓存墓碑（url为空）的秒切拦截
        if not url:
            self._play_failed_cnt = getattr(self, "_play_failed_cnt", 0) + 1
            self.log.warning(
                f"【{name}】命中了死链墓碑标记，立刻拦截跳过！连续失败次数: {self._play_failed_cnt}"
            )

            if self._play_failed_cnt >= 5:
                self.log.error("连续获取歌曲失败达到5次，触发系统第一层熔断保护！")
                self._play_failed_cnt = 0
                await self.xiaomusic.handle_fatal_error(
                    self.did, "连续多次获取歌曲失败，已为您停止播放。"
                )
            else:
                await self.set_next_music_timeout(0.5, session_id=session_id)
            return

        # 2. 统一系统提示音/TTS 的白名单免探路、免墓碑机制
        is_system_or_tts = (
            "/music/tmp/" in url or "silence.mp3" in url or "xiaomusic_" in url
        )

        # 3. 极速探路器：帮小爱吃下所有的 404/401 炸弹
        if not is_system_or_tts and url and url.startswith("http") and "/proxy/" in url:
            self.log.info(f"极速探路启动，触发后端代理解析: {url}")
            is_url_ok = False
            try:
                # 给了 3.0 秒超时，让本地解析服务有足够时间反应
                timeout = aiohttp.ClientTimeout(total=3.0)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as resp:
                        # 如果 music.py 报了 404，在这里会直接被抓个正着！
                        if resp.status in (200, 206):
                            is_url_ok = True
                            self.log.info(f"探路成功！接口畅通，状态码: {resp.status}")
                        else:
                            self.log.warning(
                                f"探路发现死链！接口报错，状态码: {resp.status}"
                            )
            except Exception as e:
                self.log.warning(f"探路超时或网络异常(插件解析失败): {e}")

            # --- 探路失败（吃下404）处理逻辑 ---
            if not is_url_ok:
                # 统一步调！所有的失败全部使用全局唯一的 _play_failed_cnt 累计！
                self._play_failed_cnt = getattr(self, "_play_failed_cnt", 0) + 1
                self.log.warning(f"当前连续失败次数: {self._play_failed_cnt}")

                if self._play_failed_cnt >= 5:
                    self.log.error("连续 5 次获取歌曲死链，触发系统第二层熔断保护！")
                    self._play_failed_cnt = 0
                    await self.xiaomusic.handle_fatal_error(
                        self.did, "连续多次获取歌曲失败，已为您停止播放。"
                    )
                    return

                # 没到 5 次，静默 0.5 秒直接切下一首。小爱甚至都不知道发生过什么！
                if self.is_playing and self._last_cmd != "stop":
                    await asyncio.sleep(0.5)
                    await self._play_next()
                return

        # 4. 真正安全的下发播放阶段
        await self.group_force_stop_xiaoai()
        self.log.info(f"发送指令给小爱，开始播放: {url}")

        results = await self.group_player_play(url, name)
        if all(ele is None for ele in results):
            self._play_failed_cnt = getattr(self, "_play_failed_cnt", 0) + 1
            self.log.info(f"播放指令发送失败. 连续失败次数: {self._play_failed_cnt}")
            await asyncio.sleep(1)
            if (
                self.is_playing
                and self._last_cmd != "stop"
                and self._play_failed_cnt < 5
            ):
                await self._play_next()
            return

        if not self._is_current_session(session_id):
            self.log.info(
                f"播放会话已过期，停止后续状态更新 did:{self.did} session:{session_id} current:{self._play_session_id}"
            )
            return

        self.is_playing = True
        self.device.cur_music = name
        self.device.playlist2music[self.device.cur_playlist] = name
        self._sync_group_state_to_devices()
        self.log.info(f"cur_music {self.get_cur_music()}")
        self.log.info(f"【{name}】已经开始播放了")

        # 记录歌曲开始播放的时间
        self._start_time = time.time()
        self._paused_time = 0

        # 获取音频时长
        sec = await self.xiaomusic.music_library.get_music_duration(name, cur_playlist)
        self._duration = sec
        await self.xiaomusic.analytics.send_play_event(name, sec, self.hardware)

        is_radio = self.xiaomusic.music_library.is_web_radio_music(name)

        # 5. 时长质检阶段：拦截下载回来的残次品
        if sec <= 0.1:
            if is_radio:
                self.log.info(f"【{name}】是电台流，无限时长，免跳过")
                self._play_failed_cnt = 0
            else:
                self._play_failed_cnt = getattr(self, "_play_failed_cnt", 0) + 1
                self.log.warning(
                    f"【{name}】资源无效(获取时长为 {sec})，触发自动跳过。连续失败次数: {self._play_failed_cnt}"
                )

                if self._play_failed_cnt >= 5:
                    self.log.error(
                        "连续获取歌曲失败达到 5 次，触发第一层终极熔断保护！"
                    )
                    self._play_failed_cnt = 0
                    asyncio.ensure_future(
                        self.xiaomusic.handle_fatal_error(
                            self.did, "连续多次获取歌曲失败，已为您停止播放。"
                        )
                    )
                else:
                    await self.set_next_music_timeout(0.5, session_id=session_id)
            return

        # 只有通过了 404 探路存活 -> 发送指令成功 -> 质检测出时长正常，才允许重置清零！
        self._play_failed_cnt = 0

        # 计算自动添加歌曲的延迟时间
        if sec > 30:
            sleep_sec = min(sec / 2, 60)
            await self.auto_add_song(cur_playlist, sleep_sec)

        # 计算获取时长的执行耗时
        duration_execution_time = time.time() - self._start_time
        self.log.info(f"获取音乐时长耗时: {duration_execution_time:.3f} 秒")
        # 调整定时器时长，减去获取音乐时长的执行时间
        adjusted_sec = sec + self.config.delay_sec - duration_execution_time
        # 确保调整后的时长不会过小，最小保留0.1秒
        adjusted_sec = max(adjusted_sec, 0.1)
        self.log.info(
            f"原始歌曲时长: {sec:.3f} 秒, 调整后定时器时长: {adjusted_sec:.3f} 秒"
        )
        await self.set_next_music_timeout(adjusted_sec, session_id=session_id)
        # 发布设备配置变更事件
        if self.event_bus:
            self.event_bus.publish(DEVICE_CONFIG_CHANGED)

        # --- 🌟 新增：触发预缓存下一首 🌟 ---
        # 如果当前歌曲大于 2 秒，则在播放 20 秒后悄悄去下载下一首歌
        if sec > 20:
            await self.prefetch_next_song(20, session_id=session_id)

    async def do_tts(self, value):
        """执行TTS（文字转语音）"""
        self.log.info(f"try do_tts value:{value}")
        if not value:
            self.log.info("do_tts no value")
            return

        # await self.group_force_stop_xiaoai()
        await self.text_to_speech(value)

        # 最大等8秒
        sec = min(8, int(len(value) / 3))
        await asyncio.sleep(sec)
        self.log.info(f"do_tts ok. cur_music:{self.get_cur_music()}")
        await self.check_replay()

    async def force_stop_xiaoai(self, device_id):
        """强制停止小爱播放"""
        try:
            ret = await self.auth_manager.mina_service.player_pause(device_id)
            self.log.info(
                f"force_stop_xiaoai player_pause device_id:{device_id} ret:{ret}"
            )
            await self.stop_if_xiaoai_is_playing(device_id)
        except Exception as e:
            self.log.warning(f"Execption {e}")

    async def get_if_xiaoai_is_playing(self):
        """检查小爱是否正在播放"""
        playing_info = await self.auth_manager.mina_service.player_get_status(
            self.device_id
        )
        self.log.info(playing_info)
        # WTF xiaomi api
        is_playing = (
            json.loads(playing_info.get("data", {}).get("info", "{}")).get("status", -1)
            == 1
        )
        return is_playing

    async def stop_if_xiaoai_is_playing(self, device_id):
        """如果小爱正在播放则停止"""
        is_playing = await self.get_if_xiaoai_is_playing()
        if is_playing or self.config.enable_force_stop:
            # stop it
            ret = await self.auth_manager.mina_service.player_stop(device_id)
            self.log.info(
                f"stop_if_xiaoai_is_playing player_stop device_id:{device_id} enable_force_stop:{self.config.enable_force_stop} ret:{ret}"
            )

    def isdownloading(self):
        """检查是否正在下载"""
        if not self._download_proc:
            return False

        if self._download_proc.returncode is not None:
            self.log.info(
                f"Process exited with returncode:{self._download_proc.returncode}"
            )
            return False

        self.log.info("Download Process is still running.")
        return True

    async def download(self, search_key, name):
        """下载歌曲"""
        if self._download_proc:
            try:
                self._download_proc.kill()
            except ProcessLookupError:
                pass

        sbp_args = (
            "yt-dlp",
            f"{self.config.search_prefix}{search_key}",
            "-x",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "--paths",
            self.config.download_path,
            "-o",
            f"{name}.mp3",
            "--ffmpeg-location",
            f"{self.ffmpeg_location}",
            "--no-playlist",
        )

        if self.config.proxy:
            sbp_args += ("--proxy", f"{self.config.proxy}")

        if self.config.enable_yt_dlp_cookies:
            sbp_args += ("--cookies", f"{self.config.yt_dlp_cookies_path}")

        if self.config.loudnorm:
            sbp_args += ("--postprocessor-args", f"-af {self.config.loudnorm}")

        cmd = " ".join(sbp_args)
        self.log.info(f"download cmd: {cmd}")
        self._download_proc = await asyncio.create_subprocess_exec(*sbp_args)
        await self.do_tts(f"正在下载歌曲{search_key}")
        self.log.info(f"正在下载中 {search_key} {name}")
        await self._download_proc.wait()
        # 下载完成后，修改文件权限
        file_path = os.path.join(self.config.download_path, f"{name}.mp3")
        chmodfile(file_path)

    async def check_replay(self):
        """检查是否需要继续播放被打断的歌曲"""
        if self.is_playing and not self.isdownloading():
            if not self.config.continue_play:
                # 重新播放歌曲
                self.log.info("现在重新播放歌曲")
                await self._play()
            else:
                self.log.info(
                    f"继续播放歌曲. self.config.continue_play:{self.config.continue_play}"
                )
        else:
            self.log.info(
                f"不会继续播放歌曲. isplaying:{self.is_playing} isdownloading:{self.isdownloading()}"
            )

    async def add_download_music(self, name):
        """把下载的音乐加入播放列表"""
        filepath = os.path.join(self.config.download_path, f"{name}.mp3")
        self.xiaomusic.music_library.all_music[name] = filepath
        # 应该很快，阻塞运行
        await self.xiaomusic.music_library._gen_all_music_tag({name: filepath})
        if name not in self._play_list:
            self._play_list.append(name)
            self.log.info(f"add_download_music add_music {name}")
            self.log.debug(self._play_list)

    def get_music(self, direction="next"):
        """获取下一首或上一首音乐"""
        self.update_playlist()
        play_list_len = len(self._play_list)
        if play_list_len == 0:
            self.log.warning("当前播放列表没有歌曲")
            return ""
        index = 0
        try:
            index = self._play_list.index(self.get_cur_music())
        except ValueError:
            pass

        if play_list_len == 1:
            new_index = index  # 当只有一首歌曲时保持当前索引不变
        else:
            if direction == "next":
                new_index = index + 1
                if (
                    self.device.play_type == PLAY_TYPE_SEQ
                    and new_index >= play_list_len
                ):
                    self.log.info("顺序播放结束")
                    return ""
                if new_index >= play_list_len:
                    if self.device.play_type == PLAY_TYPE_RND:
                        self.log.info("当前随机列表已播放一轮，触发重新洗牌！")
                        self.update_playlist(force_reshuffle=True)
                        # 洗完牌后，当前歌曲被强行置顶在了 0，下一首必定是 1
                        new_index = 1
                    else:
                        new_index = 0
            elif direction == "prev":
                new_index = index - 1
                if new_index < 0:
                    new_index = play_list_len - 1
            else:
                self.log.error("无效的方向参数")
                return ""

        name = self._play_list[new_index]
        if not self.xiaomusic.music_library.is_music_exist(name):
            self._play_list.pop(new_index)
            self.log.info(f"pop not exist music: {name}")
            return self.get_music(direction)
        return name

    def get_next_music(self):
        """获取下一首音乐"""
        return self.get_music(direction="next")

    def get_prev_music(self):
        """获取上一首音乐"""
        return self.get_music(direction="prev")

    def check_play_next(self):
        """判断是否需要播放下一首歌曲"""
        # 当前歌曲不在当前播放列表
        if self.get_cur_music() not in self._play_list:
            self.log.info(f"当前歌曲 {self.get_cur_music()} 不在当前播放列表")
            return True

        # 当前没我在播放的歌曲
        if self.get_cur_music() == "":
            self.log.info("当前没我在播放的歌曲")
            return True
        else:
            # 当前播放的歌曲不存在了
            if not self.xiaomusic.music_library.is_music_exist(self.get_cur_music()):
                self.log.info(f"当前播放的歌曲 {self.get_cur_music()} 不存在了")
                return True
        return False

    async def text_to_speech(self, value):
        """文字转语音"""
        try:
            # 检查设置中是否启用了语音TTS。如果是关闭，直接退出，避免后续走到小米TTS，导致token失效
            if self.config.edge_tts_voice == "disable":
                return
            # 检查是否配置了 edge-tts 语音角色
            elif self.config.edge_tts_voice:
                await self._text_to_speech_edge_tts(value)
            else:
                # 使用原有的 TTS 逻辑
                # 有 tts command 优先使用 tts command 说话
                if self.hardware in TTS_COMMAND:
                    tts_cmd = TTS_COMMAND[self.hardware]
                    self.log.info("Call MiIOService tts.")
                    value = value.replace(" ", ",")  # 不能有空格
                    await miio_command(
                        self.auth_manager.miio_service,
                        self.did,
                        f"{tts_cmd} {value}",
                    )
                else:
                    self.log.debug("Call MiNAService tts.")
                    await self.auth_manager.mina_service.text_to_speech(
                        self.device_id, value
                    )
        except Exception as e:
            self.log.exception(f"Execption {e}")

    async def _text_to_speech_edge_tts(self, value):
        """使用 edge-tts 进行文字转语音"""
        from xiaomusic.utils.music_utils import get_local_music_duration
        from xiaomusic.utils.network_utils import text_to_mp3

        self.log.info(f"_text_to_speech_edge_tts {value}")
        try:
            # 取消之前的 TTS 定时器
            if self._tts_timer:
                self._tts_timer.cancel()
                self._tts_timer = None
                self.log.info("已取消之前的 TTS 定时器")

            # 使用 edge-tts 生成 MP3 文件
            self.log.info(
                f"使用 edge-tts 生成语音: {value}, voice: {self.config.edge_tts_voice}"
            )
            mp3_path = await text_to_mp3(
                text=value,
                save_dir=self.config.temp_dir,
                voice=self.config.edge_tts_voice,
            )
            self.log.info(f"edge-tts 生成的文件路径: {mp3_path}")

            # 生成播放 URL
            url = self.xiaomusic.music_library._get_file_url(mp3_path)
            self.log.info(f"TTS 播放 URL: {url}")

            # 播放 TTS 音频
            await self.group_player_play(url)

            # 获取 MP3 时长
            duration = await get_local_music_duration(mp3_path, self.config)
            self.log.info(f"TTS 音频时长: {duration} 秒")

            # 创建定时器，时长到后停止
            if duration > 0:

                async def _tts_timeout():
                    await asyncio.sleep(duration)
                    try:
                        self.log.info("TTS 播放定时器时间到")
                        current_timer = self._tts_timer
                        if current_timer:
                            # 取消任务（防止任务被重复触发，即使sleep已结束）
                            current_timer.cancel()
                            try:
                                await current_timer  # 等待任务取消完成，避免警告
                            except asyncio.CancelledError:
                                pass
                            # 再置空引用
                            self._tts_timer = None
                            await self.stop(arg1="notts")
                    except Exception as e:
                        self.log.error(f"TTS 定时器异常: {e}")

                self._tts_timer = asyncio.create_task(_tts_timeout())
                self.log.info(f"已设置 TTS 定时器，{duration} 秒后停止")

        except Exception as e:
            self.log.exception(f"edge-tts 播放失败: {e}")

    async def _prewarm_play_url(self, url):
        """播放前轻量预热 HTTP URL，降低多设备同时首读时的随机卡顿。"""
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"Range": "bytes=0-0"},
                    timeout=aiohttp.ClientTimeout(total=2),
                ) as response:
                    await response.read()
                    self.log.info(
                        f"prewarm_play_url status:{response.status} url:{url}"
                    )
        except Exception as e:
            self.log.warning(f"prewarm_play_url failed url:{url} error:{e}")

    def _get_local_music_file_from_url(self, url):
        """如果 URL 指向本服务的本地 /music/ 文件，返回本地文件路径；否则返回 None。"""
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return None

        try:
            parsed = urllib.parse.urlparse(url)
            path = urllib.parse.unquote(parsed.path or "")
            if not path.startswith("/music/"):
                return None
            rel_path = path[len("/music/") :]
            # 只对真正的本地音乐库文件做分轨；TTS/转换临时文件/报错提示音等 temp 文件不处理。
            if rel_path.startswith("temp/"):
                return None

            music_base = Path(self.config.music_path).resolve()
            local_path = (music_base / rel_path).resolve()
            if not str(local_path).startswith(str(music_base)):
                return None
            if not local_path.exists() or not local_path.is_file():
                return None
            return local_path
        except Exception as e:
            self.log.warning(f"stereo_split local url check failed url:{url} error:{e}")
            return None

    def _build_temp_music_url(self, relative_temp_path):
        quoted = urllib.parse.quote(relative_temp_path.replace(os.sep, "/"), safe="/")
        url = f"{self.config.get_public_base_url()}/music/temp/{quoted}"
        return try_add_access_control_param(self.config, url)

    def _get_stereo_split_roles(self, device_id_list):
        """返回 {device_id: 'left'|'right'}。未配置左右 did 时，按组内顺序默认第一只左、第二只右。"""
        device_manager = self.xiaomusic.device_manager
        device_id_to_did = {device_id: device_manager.get_did(device_id) for device_id in device_id_list}
        left_did = (self.config.stereo_split_left_did or "").strip()
        right_did = (self.config.stereo_split_right_did or "").strip()

        if left_did and right_did:
            roles = {}
            for device_id, did in device_id_to_did.items():
                if did == left_did:
                    roles[device_id] = "left"
                elif did == right_did:
                    roles[device_id] = "right"
            if len(roles) == 2:
                return roles
            self.log.warning(
                f"stereo_split configured did not match group devices left:{left_did} right:{right_did} group:{device_id_to_did}"
            )

        if len(device_id_list) == 2:
            return {device_id_list[0]: "left", device_id_list[1]: "right"}
        return {}

    def _cleanup_stereo_split_cache(self, cache_dir: Path, keep_paths=None):
        """按最近使用时间清理左右分轨缓存。keep_paths 内文件本次播放保留。"""
        max_mb = int(getattr(self.config, "stereo_split_cache_max_mb", 0) or 0)
        if max_mb <= 0 or not cache_dir.exists():
            return
        keep = {Path(p).resolve() for p in (keep_paths or [])}
        files = [p for p in cache_dir.glob("*.mp3") if p.is_file()]
        total = sum(p.stat().st_size for p in files)
        limit = max_mb * 1024 * 1024
        if total <= limit:
            return
        removed = []
        for p in sorted(files, key=lambda x: x.stat().st_atime_ns):
            if p.resolve() in keep:
                continue
            try:
                size = p.stat().st_size
                p.unlink()
                total -= size
                removed.append(p.name)
                if total <= limit:
                    break
            except Exception as e:
                self.log.warning(f"stereo_split cache cleanup failed file:{p} error:{e}")
        if removed:
            self.log.info(
                f"stereo_split cache cleanup removed:{len(removed)} total_left_mb:{total / 1024 / 1024:.1f} limit_mb:{max_mb}"
            )

    async def _ensure_stereo_split_files(self, local_path: Path):
        """生成并缓存左右声道文件，返回 {'left': url, 'right': url}。"""
        stat = local_path.stat()
        cache_key = hashlib.sha1(
            f"{local_path}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
        ).hexdigest()[:24]
        cache_root_name = (self.config.stereo_split_cache_dir or "stereo_split").strip("/")
        temp_base = Path(self.config.temp_path).resolve()
        cache_dir = (temp_base / cache_root_name).resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)

        left_path = cache_dir / f"{cache_key}.left.mp3"
        right_path = cache_dir / f"{cache_key}.right.mp3"
        if left_path.exists() and right_path.exists() and left_path.stat().st_size > 0 and right_path.stat().st_size > 0:
            self.log.info(f"stereo_split cache hit file:{local_path}")
        else:
            ffmpeg = shutil.which("ffmpeg")
            configured_ffmpeg = Path(self.ffmpeg_location) / "ffmpeg"
            if not ffmpeg and configured_ffmpeg.exists():
                ffmpeg = str(configured_ffmpeg)
            if not ffmpeg:
                raise RuntimeError("ffmpeg not found for stereo split")

            tmp_left = left_path.with_suffix(".left.tmp.mp3")
            tmp_right = right_path.with_suffix(".right.tmp.mp3")

            async def run_ffmpeg(output_path, audio_filter):
                proc = await asyncio.create_subprocess_exec(
                    ffmpeg,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(local_path),
                    "-vn",
                    "-af",
                    audio_filter,
                    "-codec:a",
                    "libmp3lame",
                    "-q:a",
                    "2",
                    str(output_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"ffmpeg stereo split failed role_filter:{audio_filter} stderr:{stderr.decode('utf-8', 'ignore')[-500:]}"
                    )

            try:
                await asyncio.gather(
                    run_ffmpeg(tmp_left, "pan=stereo|c0=c0|c1=c0"),
                    run_ffmpeg(tmp_right, "pan=stereo|c0=c1|c1=c1"),
                )
                os.replace(tmp_left, left_path)
                os.replace(tmp_right, right_path)
            finally:
                for tmp_path in (tmp_left, tmp_right):
                    if tmp_path.exists():
                        try:
                            tmp_path.unlink()
                        except Exception:
                            pass
            chmodfile(str(left_path))
            chmodfile(str(right_path))
            self.log.info(f"stereo_split cache generated file:{local_path}")

        # 用 utime 更新 atime/mtime，便于 LRU 清理在部分 noatime 文件系统上也有效。
        now = time.time()
        for p in (left_path, right_path):
            try:
                os.utime(p, (now, p.stat().st_mtime))
            except Exception:
                pass
        self._cleanup_stereo_split_cache(cache_dir, keep_paths=[left_path, right_path])

        return {
            "left": self._build_temp_music_url(f"{cache_root_name}/{left_path.name}"),
            "right": self._build_temp_music_url(f"{cache_root_name}/{right_path.name}"),
        }

    async def prefetch_stereo_split_for_music(self, music_name):
        """后台预生成下一首本地音乐的左右分轨缓存，不下发播放指令。"""
        if not self.config.stereo_split_enabled:
            return
        if not (self.config.group_list or "").strip():
            return
        device_id_list = self.xiaomusic.device_manager.get_group_device_id_list(
            self.group_name
        )
        if len(device_id_list) != 2:
            return
        roles = self._get_stereo_split_roles(device_id_list)
        if set(roles.values()) != {"left", "right"}:
            return

        try:
            cur_playlist = self.device.cur_playlist
            url, _ = await self.xiaomusic.music_library.get_music_url(
                music_name, cur_playlist
            )
            local_path = self._get_local_music_file_from_url(url)
            if not local_path:
                return
            split_urls = await self._ensure_stereo_split_files(local_path)
            await asyncio.gather(*(self._prewarm_play_url(u) for u in split_urls.values()))
            self.log.info(
                f"stereo_split prefetch completed music:{music_name} urls:{split_urls}"
            )
        except Exception as e:
            self.log.warning(f"stereo_split prefetch failed music:{music_name} error:{e}")

    async def _try_group_stereo_split_play(self, url, name, device_id_list):
        """实验性本地音乐左右分轨：仅对启用配置、同组两设备、本地音乐 URL 生效。"""
        if not self.config.stereo_split_enabled:
            return None
        if len(device_id_list) != 2:
            return None
        # 只有显式配置 group_list 的设备组才启用，避免单设备或默认按设备名分组时误触发。
        if not (self.config.group_list or "").strip():
            return None
        if self.group_name not in self.xiaomusic.device_manager.groups:
            return None

        local_path = self._get_local_music_file_from_url(url)
        if not local_path:
            return None
        roles = self._get_stereo_split_roles(device_id_list)
        if set(roles.values()) != {"left", "right"}:
            return None

        try:
            split_urls = await self._ensure_stereo_split_files(local_path)
            # 方案 C：分轨已准备好后，再统一停止两只音箱，短暂等待固件状态落稳，随后预热并并发下发。
            await self.group_force_stop_xiaoai()
            await asyncio.sleep(self._stereo_split_stop_settle_sec)
            await asyncio.gather(*(self._prewarm_play_url(u) for u in split_urls.values()))
            tasks = [
                self.play_one_url(device_id, split_urls[roles[device_id]], name)
                for device_id in device_id_list
            ]
            results = await asyncio.gather(*tasks)
            self.log.info(
                f"group_player_play stereo_split source:{url} roles:{roles} urls:{split_urls} results:{results}"
            )
            return results
        except Exception as e:
            self.log.exception(f"stereo_split failed, fallback to normal group play: {e}")
            return None

    async def _run_bluetooth_combo_stop_command(self):
        """执行蓝牙立体声组合停止命令，用于暂停/停止当前宿主机 mpv 播放。"""
        if not self.config.bluetooth_combo_enabled:
            return None
        stop_command = (self.config.bluetooth_combo_stop_command or "").strip()
        if not stop_command:
            return None
        self.log.info(f"bluetooth_combo stop command: {stop_command}")
        try:
            proc = await asyncio.create_subprocess_shell(
                stop_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.config.bluetooth_combo_timeout_sec
            )
            stdout_text = stdout.decode("utf-8", "ignore")[-1000:]
            stderr_text = stderr.decode("utf-8", "ignore")[-1000:]
            if proc.returncode != 0:
                self.log.warning(
                    f"bluetooth_combo stop command failed rc:{proc.returncode} stdout:{stdout_text} stderr:{stderr_text}"
                )
                return None
            self.log.info(
                f"bluetooth_combo stop command ok rc:{proc.returncode} stdout:{stdout_text} stderr:{stderr_text}"
            )
            return {"bluetooth_combo_stop": True, "returncode": proc.returncode}
        except Exception as e:
            self.log.warning(f"bluetooth_combo stop command exception: {e}")
            return None

    async def _run_bluetooth_combo_command(self, url, name):
        """通过配置的本地命令播放到蓝牙立体声组合。

        命令模板支持 {url} 和 {name}，例如：
        XIAOMUSIC_BLUETOOTH_COMBO_COMMAND="/app/bin/play-bluetooth-combo {url}"
        """
        if not self.config.bluetooth_combo_enabled:
            return None
        command_template = (self.config.bluetooth_combo_command or "").strip()
        if not command_template:
            self.log.warning("bluetooth_combo enabled but command is empty")
            return None

        stop_command = (self.config.bluetooth_combo_stop_command or "").strip()
        if stop_command:
            await self._run_bluetooth_combo_stop_command()

        values = {"url": shlex.quote(url), "name": shlex.quote(name or "")}
        try:
            command = command_template.format_map(values)
        except (KeyError, ValueError) as e:
            self.log.error(f"bluetooth_combo command template invalid: {e}")
            return None

        self.log.info(f"bluetooth_combo play command: {command}")
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.config.bluetooth_combo_timeout_sec
            )
            stdout_text = stdout.decode("utf-8", "ignore")[-1000:]
            stderr_text = stderr.decode("utf-8", "ignore")[-1000:]
            if proc.returncode != 0:
                self.log.warning(
                    f"bluetooth_combo command failed rc:{proc.returncode} stdout:{stdout_text} stderr:{stderr_text}"
                )
                return None
            self.log.info(
                f"bluetooth_combo command ok rc:{proc.returncode} stdout:{stdout_text} stderr:{stderr_text}"
            )
            return {"bluetooth_combo": True, "returncode": proc.returncode}
        except Exception as e:
            self.log.exception(f"bluetooth_combo command exception: {e}")
            return None

    async def group_player_play(self, url, name=""):
        """同一组设备播放"""
        device_id_list = self.xiaomusic.device_manager.get_group_device_id_list(
            self.group_name
        )
        bluetooth_result = await self._run_bluetooth_combo_command(url, name)
        if bluetooth_result is not None:
            return bluetooth_result

        stereo_results = await self._try_group_stereo_split_play(url, name, device_id_list)
        if stereo_results is not None:
            return stereo_results

        await self._prewarm_play_url(url)
        tasks = [
            self.play_one_url(device_id, url, name) for device_id in device_id_list
        ]
        results = await asyncio.gather(*tasks)
        self.log.info(f"group_player_play {url} {device_id_list} {results}")
        return results

    async def play_one_url(self, device_id, url, name):
        """在单个设备上播放URL"""
        ret = None
        try:
            audio_id = await self._get_audio_id(name)
            if self.config.continue_play:
                ret = await self.auth_manager.mina_service.play_by_music_url(
                    device_id, url, _type=1, audio_id=audio_id
                )
                self.log.info(
                    f"play_one_url continue_play device_id:{device_id} ret:{ret} url:{url} audio_id:{audio_id}"
                )
            elif self.config.use_music_api or (
                self.hardware in NEED_USE_PLAY_MUSIC_API
            ):
                ret = await self.auth_manager.mina_service.play_by_music_url(
                    device_id, url, audio_id=audio_id
                )
                self.log.info(
                    f"play_one_url play_by_music_url device_id:{device_id} ret:{ret} url:{url} audio_id:{audio_id}"
                )
            else:
                ret = await self.auth_manager.mina_service.play_by_url(device_id, url)
                self.log.info(
                    f"play_one_url play_by_url device_id:{device_id} ret:{ret} url:{url}"
                )
        except Exception as e:
            self.log.exception(f"Execption {e}")
        return ret

    async def _get_audio_id(self, name):
        """获取音频ID"""
        audio_id = self.config.use_music_audio_id or "1582971365183456177"
        if not (self.config.use_music_api or self.config.continue_play):
            return str(audio_id)

        # 如果 name 为空（如播放 TTS 时），坚决不请求小米接口，会导致小米账号报错。
        name = name.strip() if name else ""
        if not name:
            self.log.debug(
                "歌名为空(可能是TTS播报)，直接使用默认 audio_id，跳过小米接口查询。"
            )
            return str(audio_id)
        # 修复结束

        try:
            params = {
                "query": name,
                "queryType": 1,
                "offset": 0,
                "count": 6,
                "timestamp": int(time.time_ns() / 1000),
            }
            response = await self.auth_manager.mina_service.mina_request(
                "/music/search", params
            )
            song_list = response.get("data", {}).get("songList", [])

            if song_list:
                # 先默认拿匹配到的第一首的id垫底（容错兜底）
                audio_id = song_list[0].get("audioID")
                # 把传进来的 "歌名-歌手" 拆开
                target_song = name
                target_artist = ""
                if "-" in name:
                    parts = name.split("-", 1)
                    target_song = parts[0].strip()
                    target_artist = parts[1].strip()
                # 歌手如果有多个只取第一个去匹配
                first_artist = target_artist
                if first_artist:
                    for sep in [";", "；", ",", "，", "&", "、", "/"]:
                        first_artist = first_artist.replace(sep, "|")
                    first_artist = first_artist.split("|")[0].strip()
                # 歌名完全相等，歌手 in 包含
                for song in song_list:
                    s_name = song.get("name", "")
                    s_artist = song.get("artist", {}).get("name", "")
                    if target_song.lower() == s_name.lower():
                        if not first_artist or first_artist.lower() in s_artist.lower():
                            audio_id = song.get("audioID")
                            break

            self.log.debug(f"_get_audio_id. name: {name} 最终使用的 songId:{audio_id}")

        except Exception as e:
            self.log.error(f"_get_audio_id 获取失败: {e}")

        return str(audio_id)

    async def reset_timer_when_answer(self, answer_length):
        """重置计时器（当小爱回答时）"""
        if not (self.is_playing and self.config.continue_play):
            return
        pause_time = answer_length / 5 + 1
        offset, duration = self.get_offset_duration()
        self._paused_time += pause_time
        new_time = duration - offset + pause_time
        await self.set_next_music_timeout(new_time)
        self.log.info(
            f"reset_timer 延长定时器. answer_length:{answer_length} pause_time:{pause_time}"
        )

    async def set_next_music_timeout(self, sec, session_id=None):
        """设置下一首歌曲的播放定时器"""
        await self.cancel_next_timer()
        if session_id is None:
            session_id = self._play_session_id

        async def _do_next():
            await asyncio.sleep(sec)
            try:
                if not self._is_current_session(session_id):
                    self.log.info(
                        f"下一曲定时器已过期，跳过 did:{self.did} session:{session_id} current:{self._play_session_id}"
                    )
                    return
                self.log.info(f"定时器时间到了 did: {self.did}")
                if self._next_timer is asyncio.current_task():
                    self._next_timer = None
                if self.device.play_type == PLAY_TYPE_SIN:
                    self.log.info(f"单曲播放不继续播放下一首 did: {self.did}")
                    await self.stop(arg1="notts")
                else:
                    await self._play_next()

            except Exception as e:
                self.log.error(f"Execption {e}")

        self._next_timer = asyncio.create_task(_do_next())
        self.log.info(f"{sec} 秒后将会播放下一首歌曲 did: {self.did} session:{session_id}")

    async def set_volume(self, volume: int):
        """设置音量"""
        self.log.info(f"set_volume.  did: {self.did} volume: {volume}")
        try:
            await self.auth_manager.mina_service.player_set_volume(
                self.device_id, volume
            )
        except Exception as e:
            self.log.exception(f"Execption {e}")

    async def get_volume(self):
        """获取音量"""
        volume = 0
        try:
            playing_info = await self.auth_manager.mina_service.player_get_status(
                self.device_id
            )
            self.log.info(f"get_volume. playing_info:{playing_info}")
            volume = json.loads(playing_info.get("data", {}).get("info", "{}")).get(
                "volume", 0
            )
        except Exception as e:
            self.log.warning(f"Execption {e}")
        volume = int(volume)
        self.log.info("get_volume. volume:%d", volume)
        return volume

    async def get_player_status(self):
        """获取完整播放状态"""
        try:
            playing_info = await self.auth_manager.mina_service.player_get_status(
                self.device_id
            )
            self.log.info(f"get_player_status. playing_info:{playing_info}")
            info = json.loads(playing_info.get("data", {}).get("info", "{}"))
            return info
        except Exception as e:
            self.log.warning(f"Execption {e}")
        return {"volume": 0, "status": 0}

    async def set_play_type(self, play_type, dotts=True):
        """设置播放类型"""
        self._apply_group_state_to_device()
        self.device.play_type = play_type
        self._sync_group_state_to_devices()
        # 发布设备配置变更事件
        if self.event_bus:
            self.event_bus.publish(DEVICE_CONFIG_CHANGED)
        if dotts:
            tts = self.config.get_play_type_tts(play_type)
            await self.do_tts(tts)
        # 切换模式，强制重新洗牌
        self.update_playlist(force_reshuffle=True)
        self._sync_group_state_to_devices()

    async def play_music_list(self, list_name, music_name):
        """播放指定播放列表"""
        self._last_cmd = "play_music_list"
        self._apply_group_state_to_device()
        self.device.cur_playlist = list_name
        # 切换歌单，强制重新洗牌
        self.update_playlist(force_reshuffle=True)
        self._sync_group_state_to_devices()
        if not music_name:
            music_name = self.device.playlist2music.get(list_name, "")
        self.log.info(f"开始播放列表{list_name} {music_name}")
        await self._play(music_name)

    async def stop(self, arg1=""):
        """停止播放"""
        self._last_cmd = "stop"
        self.is_playing = False
        if arg1 != "notts":
            await self.do_tts(self.config.stop_tts_msg)
            await asyncio.sleep(3)  # 等它说完
        # 取消组内所有的下一首歌曲的定时器
        await self.cancel_group_next_timer()
        await self._run_bluetooth_combo_stop_command()
        await self.group_force_stop_xiaoai()
        self.log.info("stop now")

    async def group_force_stop_xiaoai(self):
        """强制停止组内所有设备"""
        device_id_list = self.xiaomusic.device_manager.get_group_device_id_list(
            self.group_name
        )
        self.log.info(f"group_force_stop_xiaoai {self.group_name} {device_id_list}")
        tasks = [self.force_stop_xiaoai(device_id) for device_id in device_id_list]
        results = await asyncio.gather(*tasks)
        self.log.info(f"group_force_stop_xiaoai {device_id_list} {results}")
        return results

    async def stop_after_minute(self, minute: int):
        """定时关机"""
        if self._stop_timer:
            self._stop_timer.cancel()
            self._stop_timer = None
            self.log.info("关机定时器已取消")

        async def _do_stop():
            await asyncio.sleep(minute * 60)
            try:
                await self.stop(arg1="notts")
            except Exception as e:
                self.log.exception(f"Execption {e}")

        self._stop_timer = asyncio.create_task(_do_stop())
        await self.do_tts(f"收到,{minute}分钟后将关机")

    async def cancel_next_timer(self):
        """取消下一首定时器。

        没有定时器是正常状态：首次播放、手动切歌后重新设置定时器、
        以及组播取消其他设备定时器时都会走到这里。不要在 INFO 日志里刷
        “定时器不见了”，否则容易被误判为播放异常。
        """
        if not self._next_timer:
            self.log.debug(f"无需取消下一曲定时器 did: {self.did}")
            return

        current_timer = self._next_timer
        if current_timer:
            self._next_timer = None
            current_timer.cancel()
            if current_timer is not asyncio.current_task():
                try:
                    await current_timer
                except asyncio.CancelledError:
                    pass
        self.log.info(f"下一曲定时器已取消 did: {self.did}")

    async def cancel_group_next_timer(self):
        """取消组内所有设备的下一首定时器"""
        devices = self.xiaomusic.device_manager.get_group_devices(self.group_name)
        self.log.info(f"cancel_group_next_timer {devices}")
        for device in devices.values():
            await device.cancel_next_timer()

    def get_cur_play_list(self):
        """获取当前播放列表名称"""
        return self.device.cur_playlist

    def cancel_all_timer(self):
        """清空所有定时器"""
        self.log.info("in cancel_all_timer")
        if self._next_timer:
            self._next_timer.cancel()
            self._next_timer = None
            self.log.info("cancel_all_timer _next_timer.cancel")

        if self._stop_timer:
            self._stop_timer.cancel()
            self._stop_timer = None
            self.log.info("cancel_all_timer _stop_timer.cancel")

        if self._tts_timer:
            self._tts_timer.cancel()
            self._tts_timer = None
            self.log.info("cancel_all_timer _tts_timer.cancel")

        if self._prefetch_timer:
            self._prefetch_timer.cancel()
            self._prefetch_timer = None
            self.log.info("cancel_all_timer _prefetch_timer.cancel")

    @classmethod
    def dict_clear(cls, d):
        """清空设备字典并取消所有定时器"""
        for key in list(d):
            val = d.pop(key)
            val.cancel_all_timer()

    def find_cur_playlist(self, name):
        """根据当前歌曲匹配歌曲列表

        匹配顺序：
        1. 收藏
        2. 最近新增
        3. 排除（全部,所有歌曲,所有电台）
        4. 所有歌曲
        5. 所有电台
        6. 全部
        """
        music_list = self.xiaomusic.music_library.music_list
        if name in music_list.get("收藏", []):
            return "收藏"
        if name in music_list.get("最近新增", []):
            return "最近新增"
        for list_name, play_list in music_list.items():
            if (list_name not in ["全部", "所有歌曲", "所有电台"]) and (
                name in play_list
            ):
                return list_name
        if name in music_list.get("所有歌曲", []):
            return "所有歌曲"
        if name in music_list.get("所有电台", []):
            return "所有电台"
        return "全部"

    async def handle_selection(self, index):
        """处理用户选择第几个歌曲

        Args:
            index: 用户选择的序号（从1开始）
        """
        self._apply_group_state_to_device()
        if (
            not self._pending_selection
            or index < 1
            or index > len(self._pending_selection)
        ):
            await self.xiaomusic.do_tts(self.did, "选择无效")
            return

        selected_name = self._pending_selection[index - 1]
        self.log.info(f"用户选择了第{index}个: {selected_name}")
        # 保持待选择状态不变，支持用户继续选择其他歌曲
        await self._playmusic(selected_name)
