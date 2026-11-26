"""Item photos: resize, store locally, serve (BR-IMG-03/04/05).

Files live in <config>/household_shopping_images/<entry_id>/<random>.jpg, which
HA backups include. They're served without auth (as HA's own image_upload does)
because <img> tags can't send a token; names are random 128-bit ids, so they
can't be guessed.
"""

from __future__ import annotations

import base64
import binascii
import io
from pathlib import Path
import re
import shutil
from typing import TYPE_CHECKING, Any
import uuid

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import IMAGE_DIR, IMAGE_MAX_DOWNLOAD, IMAGE_MAX_PX, IMAGE_URL
from .model import ShoppingError

if TYPE_CHECKING:
    from .manager import ShoppingManager

_SAFE = re.compile(r"^[0-9a-f]{32}$")
_ENTRY = re.compile(r"^[0-9A-Za-z_]+$")


def _dir(hass: HomeAssistant, entry_id: str) -> Path:
    return Path(hass.config.path(IMAGE_DIR, entry_id))


def image_url(entry_id: str, file_id: str) -> str:
    return f"{IMAGE_URL}/{entry_id}/{file_id}.jpg"


def _process(raw: bytes) -> bytes:
    """Decode any common format, fix rotation, shrink, re-encode as JPEG."""
    from PIL import Image, ImageOps, UnidentifiedImageError  # noqa: PLC0415

    try:
        with Image.open(io.BytesIO(raw)) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((IMAGE_MAX_PX, IMAGE_MAX_PX))
            out = io.BytesIO()
            img.save(out, "JPEG", quality=82, optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError) as err:
        raise ShoppingError("That doesn't look like an image") from err


def _write(hass: HomeAssistant, entry_id: str, raw: bytes) -> str:
    data = _process(raw)
    folder = _dir(hass, entry_id)
    folder.mkdir(parents=True, exist_ok=True)
    file_id = uuid.uuid4().hex
    (folder / f"{file_id}.jpg").write_bytes(data)
    return file_id


def remove_image(hass: HomeAssistant, entry_id: str, file_id: str) -> None:
    if _SAFE.match(file_id):
        (_dir(hass, entry_id) / f"{file_id}.jpg").unlink(missing_ok=True)


async def _store(manager: ShoppingManager, raw: bytes, d: dict[str, Any]) -> None:
    hass = manager.hass
    # Check the item and the own-photo rule before doing any work.
    manager.run(lambda m: m.get_catalogue_item(d["name"]))
    file_id = await hass.async_add_executor_job(_write, hass, manager.entry_id, raw)
    old: dict[str, Any] = {}

    def apply(model: Any) -> None:
        old.update(model.get_catalogue_item(d["name"]).get("image") or {})
        model.set_image(
            d["name"],
            {
                "file": file_id,
                "url": image_url(manager.entry_id, file_id),
                "source": d.get("source", "other"),
                "attribution": d.get("attribution"),
            },
            force=d.get("force", False),
        )

    try:
        manager.run(apply)
    except Exception:
        await hass.async_add_executor_job(remove_image, hass, manager.entry_id, file_id)
        raise
    if old.get("file"):
        await hass.async_add_executor_job(remove_image, hass, manager.entry_id, old["file"])


async def async_set_image_from_url(manager: ShoppingManager, d: dict[str, Any]) -> None:
    """The one network call the integration makes, and only when asked (NFR-01)."""
    session = async_get_clientsession(manager.hass)
    try:
        async with session.get(d["image_url"], timeout=30) as resp:
            if resp.status != 200:
                raise ShoppingError(f"Couldn't download the image (HTTP {resp.status})")
            raw = await resp.content.read(IMAGE_MAX_DOWNLOAD + 1)
    except ShoppingError:
        raise
    except Exception as err:
        raise ShoppingError(f"Couldn't download the image: {err}") from err
    if len(raw) > IMAGE_MAX_DOWNLOAD:
        raise ShoppingError("That image is too large (over 10 MB)")
    await _store(manager, raw, d)


async def async_set_image_from_data(manager: ShoppingManager, d: dict[str, Any]) -> None:
    payload = d["image_data"]
    if payload.startswith("data:"):
        payload = payload.split(",", 1)[-1]
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as err:
        raise ShoppingError("image_data must be base64") from err
    if len(raw) > IMAGE_MAX_DOWNLOAD:
        raise ShoppingError("That image is too large (over 10 MB)")
    await _store(manager, raw, d)


async def async_remove_entry_images(hass: HomeAssistant, entry_id: str) -> None:
    await hass.async_add_executor_job(
        shutil.rmtree, _dir(hass, entry_id), True  # ignore_errors
    )


class ImageView(HomeAssistantView):
    url = IMAGE_URL + "/{entry_id}/{file_id}.jpg"
    name = "api:household_shopping:image"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, entry_id: str, file_id: str) -> web.StreamResponse:
        if not (_ENTRY.match(entry_id) and _SAFE.match(file_id)):
            raise web.HTTPNotFound
        path = _dir(self.hass, entry_id) / f"{file_id}.jpg"
        if not await self.hass.async_add_executor_job(path.is_file):
            raise web.HTTPNotFound
        return web.FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@callback
def async_setup_images(hass: HomeAssistant) -> None:
    if "http" in hass.config.components:
        hass.http.register_view(ImageView(hass))
