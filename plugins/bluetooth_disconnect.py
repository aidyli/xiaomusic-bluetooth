import requests


async def bluetooth_disconnect():
    global log, xiaomusic
    url = "http://127.0.0.1:58091/disconnect"
    response = requests.get(url, timeout=12)
    response.raise_for_status()
    log.info(f"bluetooth_disconnect response:{response.text}")
    did = xiaomusic.get_cur_did()
    if did:
        await xiaomusic.do_tts(did, "已断开蓝牙立体声组合")
