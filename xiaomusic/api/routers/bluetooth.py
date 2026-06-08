"""Bluetooth sidecar control routes for the local XiaoMusic deployment."""

import json
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, Query

from xiaomusic.api.dependencies import log, verification

router = APIRouter(dependencies=[Depends(verification)])

SIDECAR_BASE_URL = "http://127.0.0.1:58091"


def _call_sidecar(path: str, timeout: int = 10):
    url = f"{SIDECAR_BASE_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        return {"ret": "ERROR", "status": err.code, "error": body}
    except Exception as err:  # noqa: BLE001 - surface sidecar failure to UI
        log.exception("bluetooth sidecar request failed: %s", url)
        return {"ret": "ERROR", "error": str(err)}

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = {"raw": body}
    if isinstance(data, dict):
        data.setdefault("ret", "OK")
        return data
    return {"ret": "OK", "data": data}


@router.get("/api/bluetooth/status")
async def bluetooth_status():
    """Return sidecar health/status, including paired devices and current sink."""
    return _call_sidecar("/status", timeout=10)


@router.get("/api/bluetooth/scan")
async def bluetooth_scan(
    seconds: int = Query(20, ge=5, le=180),
    async_scan: bool = Query(False, alias="async"),
):
    """Trigger sidecar Bluetooth scan.

    For classic A2DP speakers, put the speaker/stereo group into discoverable or
    pairing mode before scanning. async=true starts the scan in the sidecar and
    returns immediately; otherwise this request waits for scan completion.
    """
    query = urllib.parse.urlencode(
        {"seconds": seconds, "async": "1" if async_scan else "0"}
    )
    return _call_sidecar(f"/scan?{query}", timeout=seconds + 20)


@router.get("/api/bluetooth/connect")
async def bluetooth_connect(
    address: str = Query(
        "", description="Bluetooth MAC address; empty uses sidecar default target"
    ),
    async_connect: bool = Query(False, alias="async"),
):
    """Connect sidecar to a scanned/trusted Bluetooth audio sink."""
    params = {"async": "1" if async_connect else "0"}
    if address:
        params["address"] = address
    query = urllib.parse.urlencode(params)
    return _call_sidecar(f"/connect?{query}", timeout=60)


@router.get("/api/bluetooth/disconnect")
async def bluetooth_disconnect():
    """Disconnect sidecar from current Bluetooth target."""
    return _call_sidecar("/disconnect", timeout=20)
