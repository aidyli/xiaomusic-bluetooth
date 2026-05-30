"""DLNA/UPnP discovery routes."""

from fastapi import APIRouter, Depends, Query

from xiaomusic.api.dependencies import verification
from xiaomusic.dlna import discover_dlna_renderers

router = APIRouter(dependencies=[Depends(verification)])


@router.get("/api/dlna/renderers")
async def dlna_renderers(
    timeout: float = Query(3.0, ge=0.5, le=10.0),
    include_all: bool = False,
):
    """Scan LAN for DLNA/UPnP media renderer candidates.

    Use this to check whether Xiaomi's official stereo group is exposed on LAN
    as a DLNA renderer. Returned devices with an AVTransport control URL are the
    most interesting candidates for later URL-cast experiments.
    """
    renderers = await discover_dlna_renderers(timeout=timeout, include_all=include_all)
    return {
        "ret": "OK",
        "count": len(renderers),
        "renderers": renderers,
        "hint": "如果米家官方立体声组作为 DLNA Renderer 暴露，通常会在 friendly_name 中出现组名，并带有 AVTransport control_url。",
    }
