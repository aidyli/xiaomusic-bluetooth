import requests


async def bluetooth_connect():
    global log, xiaomusic
    url = "http://127.0.0.1:58091/connect"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    log.info(f"bluetooth_connect response:{response.text}")
    did = xiaomusic.get_cur_did()
    if did:
        await xiaomusic.do_tts(did, "已连接蓝牙立体声组合")
