"""DLNA/UPnP discovery helpers.

This module performs a lightweight SSDP M-SEARCH scan and extracts devices that
look like media renderers. It intentionally avoids adding a third-party
runtime dependency so XiaoMusic can run in existing Docker images.
"""

from __future__ import annotations

import asyncio
import socket
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from typing import Any

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
DEFAULT_SEARCH_TARGETS = (
    "urn:schemas-upnp-org:device:MediaRenderer:1",
    "urn:schemas-upnp-org:service:AVTransport:1",
    "ssdp:all",
)


@dataclass
class DlnaRenderer:
    """A discovered DLNA/UPnP media renderer candidate."""

    usn: str = ""
    st: str = ""
    location: str = ""
    server: str = ""
    ip: str = ""
    friendly_name: str = ""
    manufacturer: str = ""
    model_name: str = ""
    device_type: str = ""
    udn: str = ""
    av_transport_control_url: str = ""
    rendering_control_url: str = ""
    services: list[dict[str, str]] = field(default_factory=list)
    raw_headers: dict[str, str] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_ssdp_response(data: bytes) -> dict[str, str]:
    """Parse SSDP response headers into a lower-case-key dict."""
    text = data.decode("utf-8", "ignore")
    headers: dict[str, str] = {}
    for line in text.split("\r\n"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def _join_url(base_url: str, control_url: str) -> str:
    """Resolve UPnP controlURL against the device description URL."""
    if not control_url:
        return ""
    return urllib.parse.urljoin(base_url, control_url)


def _tag_name(element: ET.Element) -> str:
    """Return local XML tag name without namespace."""
    return element.tag.rsplit("}", 1)[-1]


def _find_child_text(element: ET.Element, name: str) -> str:
    """Find first child text by local tag name."""
    for child in element.iter():
        if _tag_name(child) == name and child.text:
            return child.text.strip()
    return ""


def _extract_services(root: ET.Element, location: str) -> list[dict[str, str]]:
    services: list[dict[str, str]] = []
    for service in root.iter():
        if _tag_name(service) != "service":
            continue
        service_info: dict[str, str] = {}
        for child in service:
            service_info[_tag_name(child)] = (child.text or "").strip()
        service_type = service_info.get("serviceType", "")
        control_url = service_info.get("controlURL", "")
        services.append(
            {
                "service_type": service_type,
                "service_id": service_info.get("serviceId", ""),
                "control_url": _join_url(location, control_url),
                "event_sub_url": _join_url(
                    location, service_info.get("eventSubURL", "")
                ),
                "scpd_url": _join_url(location, service_info.get("SCPDURL", "")),
            }
        )
    return services


def _looks_like_renderer(headers: dict[str, str], renderer: DlnaRenderer) -> bool:
    haystack = " ".join(
        [
            headers.get("st", ""),
            headers.get("usn", ""),
            renderer.device_type,
            " ".join(service.get("service_type", "") for service in renderer.services),
        ]
    ).lower()
    return "mediarenderer" in haystack or "avtransport" in haystack


def _fetch_description_sync(renderer: DlnaRenderer, timeout: float) -> DlnaRenderer:
    """Fetch and parse UPnP device description using stdlib urllib."""
    if not renderer.location:
        renderer.error = "missing LOCATION header"
        return renderer
    try:
        request = urllib.request.Request(
            renderer.location,
            headers={"User-Agent": "XiaoMusic/UPnP-DLNA-Discovery"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            if status >= 400:
                renderer.error = f"description http status {status}"
                return renderer
            body = resp.read(1024 * 1024)
    except Exception as exc:
        renderer.error = f"description fetch failed: {exc}"
        return renderer

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        renderer.error = f"description xml parse failed: {exc}"
        return renderer

    renderer.friendly_name = _find_child_text(root, "friendlyName")
    renderer.manufacturer = _find_child_text(root, "manufacturer")
    renderer.model_name = _find_child_text(root, "modelName")
    renderer.device_type = _find_child_text(root, "deviceType")
    renderer.udn = _find_child_text(root, "UDN")
    renderer.services = _extract_services(root, renderer.location)
    for service in renderer.services:
        service_type = service.get("service_type", "")
        if "AVTransport" in service_type:
            renderer.av_transport_control_url = service.get("control_url", "")
        elif "RenderingControl" in service_type:
            renderer.rendering_control_url = service.get("control_url", "")
    return renderer


async def _fetch_description(renderer: DlnaRenderer, timeout: float) -> DlnaRenderer:
    """Async wrapper for blocking urllib description fetch."""
    return await asyncio.to_thread(_fetch_description_sync, renderer, timeout)


async def discover_dlna_renderers(
    timeout: float = 3.0,
    mx: int = 2,
    search_targets: tuple[str, ...] = DEFAULT_SEARCH_TARGETS,
    include_all: bool = False,
) -> list[dict[str, Any]]:
    """Discover DLNA/UPnP media renderer candidates on the local network.

    Args:
        timeout: Total SSDP listening time in seconds.
        mx: SSDP MX header value. Devices respond within this window.
        search_targets: SSDP search targets to query.
        include_all: Return all devices even when they do not look like renderers.

    Returns:
        List of renderer dictionaries safe for JSON responses.
    """
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setblocking(False)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        for st in search_targets:
            msg = (
                "M-SEARCH * HTTP/1.1\r\n"
                f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
                'MAN: "ssdp:discover"\r\n'
                f"MX: {max(1, int(mx))}\r\n"
                f"ST: {st}\r\n"
                "\r\n"
            ).encode("ascii")
            await loop.sock_sendto(sock, msg, (SSDP_ADDR, SSDP_PORT))

        responses: dict[str, DlnaRenderer] = {}
        deadline = time.monotonic() + max(0.5, float(timeout))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                data, addr = await asyncio.wait_for(
                    loop.sock_recvfrom(sock, 65535), remaining
                )
            except TimeoutError:
                break
            headers = _parse_ssdp_response(data)
            location = headers.get("location", "")
            usn = headers.get("usn", "")
            key = location or usn or f"{addr[0]}:{addr[1]}"
            if key in responses:
                continue
            responses[key] = DlnaRenderer(
                usn=usn,
                st=headers.get("st", ""),
                location=location,
                server=headers.get("server", ""),
                ip=addr[0],
                raw_headers=headers,
            )
    finally:
        sock.close()

    enriched = await asyncio.gather(
        *(_fetch_description(renderer, timeout=2.0) for renderer in responses.values())
    )

    result = []
    for renderer in enriched:
        if include_all or _looks_like_renderer(renderer.raw_headers, renderer):
            result.append(renderer.to_dict())
    result.sort(
        key=lambda item: item.get("friendly_name") or item.get("location") or ""
    )
    return result
