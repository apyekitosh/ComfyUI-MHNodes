"""Reading video files, and what the loaders' previews need from the server.

The preview never re-encodes per adjustment. The browser plays the file itself and the frontend
only moves the start and end of what it loops, so changing start, frame_cap or select_every_nth
costs nothing. The server is involved once per file: to read its frame rate, which browsers do
not expose, and -- only for files a browser cannot play, such as ProRes -- to build a small
H.264 proxy, cached in temp until the next restart.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
from fractions import Fraction

log = logging.getLogger("MHNodes.VideoStore")

VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".gif", ".mpg", ".mpeg", ".wmv", ".flv"}
#: Containers Chromium plays directly, given a codec it can decode.
PLAYABLE_CONTAINERS = {".mp4", ".m4v", ".mov", ".webm"}
PROXY_SUBFOLDER = "mh_video_proxy"
PROXY_LONG_SIDE = 640

_proxy_locks: dict[str, threading.Lock] = {}
_proxy_locks_guard = threading.Lock()


def clean_path(value: str) -> str:
    """A pasted path, with the quotes Windows' "Copy as path" adds taken off."""
    return (value or "").strip().strip('"').strip("'").strip()


def is_video_path(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS


def input_videos() -> list[str]:
    """Video files at the top of the input folder, as core's own Load Video lists them."""
    import folder_paths

    base = folder_paths.get_input_directory()
    files = [f for f in os.listdir(base) if os.path.isfile(os.path.join(base, f))]
    return sorted(folder_paths.filter_files_content_types(files, ["video"]))


def frame_rate(stream) -> Fraction:
    rate = stream.average_rate or stream.guessed_rate or stream.base_rate
    return Fraction(rate) if rate else Fraction(24)


def probe(path: str) -> dict:
    """What the preview and the loader need to know, read from the header (no decoding)."""
    import av

    with av.open(path) as container:
        if not container.streams.video:
            raise ValueError(f"{os.path.basename(path)} has no video stream.")
        stream = container.streams.video[0]
        fps = frame_rate(stream)
        if container.duration:
            duration = container.duration / 1_000_000
        elif stream.duration and stream.time_base:
            duration = float(stream.duration * stream.time_base)
        else:
            duration = 0.0
        frames = stream.frames or round(duration * fps)
        codec = stream.codec_context.name
        pix_fmt = stream.codec_context.pix_fmt or ""
        return {
            "fps": float(fps),
            "frames": int(frames),
            "duration": duration,
            "width": stream.codec_context.width,
            "height": stream.codec_context.height,
            "codec": codec,
            "pix_fmt": pix_fmt,
            "has_audio": bool(container.streams.audio),
            "playable": _browser_playable(path, codec, pix_fmt),
        }


def _browser_playable(path: str, codec: str, pix_fmt: str) -> bool:
    if os.path.splitext(path)[1].lower() not in PLAYABLE_CONTAINERS:
        return False
    if codec in ("vp8", "vp9", "av1"):
        return True
    # Browsers decode 8-bit 4:2:0 H.264 only; 4:2:2, 4:4:4 and 10-bit profiles fail silently.
    return codec == "h264" and pix_fmt in ("yuv420p", "yuvj420p")


# ---------------------------------------------------------------- proxy

def _proxy_name(path: str) -> str:
    stat = os.stat(path)
    key = f"{os.path.abspath(path)}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:20] + ".mp4"


def proxy_dir() -> str:
    import folder_paths

    path = os.path.join(folder_paths.get_temp_directory(), PROXY_SUBFOLDER)
    os.makedirs(path, exist_ok=True)
    return path


def ensure_proxy(path: str) -> str:
    """A small H.264 copy of a video the browser can't play. Built once per file version.

    Same frame rate and frame count as the source, so frame n of the proxy is frame n of the
    file and the preview's range lines up with what the loader returns.
    """
    name = _proxy_name(path)
    target = os.path.join(proxy_dir(), name)
    if os.path.isfile(target):
        return name

    with _proxy_locks_guard:
        lock = _proxy_locks.setdefault(name, threading.Lock())
    with lock:
        if not os.path.isfile(target):
            partial = target + ".part"
            try:
                _write_proxy(path, partial)
                os.replace(partial, target)
            finally:
                if os.path.exists(partial):
                    os.remove(partial)
    return name


def _even(value: int) -> int:
    return max(2, value - value % 2)


def _write_proxy(source: str, target: str) -> None:
    import av

    with av.open(source) as inp, av.open(target, "w", format="mp4") as out:
        vin = inp.streams.video[0]
        vin.thread_type = "AUTO"
        fps = frame_rate(vin)
        width, height = vin.codec_context.width, vin.codec_context.height
        scale = min(1.0, PROXY_LONG_SIDE / max(width, height))
        width, height = _even(round(width * scale)), _even(round(height * scale))

        vout = out.add_stream("libx264", rate=fps)
        vout.width, vout.height, vout.pix_fmt = width, height, "yuv420p"
        vout.options = {"crf": "26", "preset": "veryfast"}
        vout.codec_context.time_base = 1 / fps

        ain = inp.streams.audio[0] if inp.streams.audio else None
        aout = resampler = None
        if ain is not None:
            rate = ain.codec_context.sample_rate or 48000
            aout = out.add_stream("aac", rate=rate, layout="stereo")
            resampler = av.AudioResampler(format="fltp", layout="stereo", rate=rate)

        streams = [vin] + ([ain] if ain is not None else [])
        index = 0
        for packet in inp.demux(*streams):
            for frame in packet.decode():
                if packet.stream.type == "video":
                    # Numbered rather than timed, so a variable-rate source still comes out
                    # one proxy frame per source frame.
                    picture = frame.reformat(width=width, height=height, format="yuv420p")
                    picture.pts, picture.time_base = index, 1 / fps
                    index += 1
                    out.mux(vout.encode(picture))
                else:
                    for chunk in resampler.resample(frame):
                        chunk.pts = None
                        out.mux(aout.encode(chunk))
        out.mux(vout.encode(None))
        if aout is not None:
            out.mux(aout.encode(None))


# ---------------------------------------------------------------- image folders

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
#: A folder's preview copy is always written at this rate; the preview plays it faster or slower
#: to match the node's fps, so changing fps never rebuilds it.
FOLDER_PREVIEW_FPS = 24


def _natural_key(name: str):
    """frame2 before frame10, as a person would sort them."""
    import re

    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def folder_images(folder: str) -> list[str]:
    """Image files directly in `folder`, in natural name order."""
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"No folder at {folder!r}.")
    names = [entry.name for entry in os.scandir(folder)
             if entry.is_file() and os.path.splitext(entry.name)[1].lower() in IMAGE_EXTENSIONS]
    return [os.path.join(folder, name) for name in sorted(names, key=_natural_key)]


def folder_signature(files: list[str]) -> str:
    """Changes whenever a frame is added, removed or rewritten."""
    digest = hashlib.sha1()
    for path in files:
        stat = os.stat(path)
        digest.update(f"{path}|{stat.st_size}|{stat.st_mtime_ns}\n".encode("utf-8"))
    return digest.hexdigest()[:20]


def open_frame(path: str, draft_size=None):
    """An image as PIL RGB, upright, with 16-bit sources scaled down rather than clipped.

    `draft_size` lets a JPEG decode at reduced size, which is most of the cost on big frames.
    It only ever gives at least that size, so the result is still resized afterwards.
    """
    from PIL import Image, ImageOps

    image = Image.open(path)
    if draft_size is not None:
        image.draft("RGB", draft_size)
    image = ImageOps.exif_transpose(image)
    if image.mode in ("I;16", "I;16B", "I;16L", "I"):
        image = image.point(lambda value: value * (1 / 256)).convert("L")
    return image.convert("RGB")


def fit(image, size):
    """Fill `size`, cropping the overflow, so a stray frame is never stretched."""
    from PIL import Image, ImageOps

    if image.size == size:
        return image
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)


def folder_info(folder: str) -> dict:
    files = folder_images(folder)
    if not files:
        raise ValueError("no images in this folder")
    from PIL import Image

    with Image.open(files[0]) as first:
        width, height = first.size
    return {"fps": FOLDER_PREVIEW_FPS, "frames": len(files), "width": width, "height": height,
            "has_audio": False, "playable": False}


def ensure_folder_proxy(folder: str) -> str:
    files = folder_images(folder)
    if not files:
        raise ValueError("no images in this folder")
    name = f"seq_{folder_signature(files)}.mp4"
    target = os.path.join(proxy_dir(), name)
    if os.path.isfile(target):
        return name

    with _proxy_locks_guard:
        lock = _proxy_locks.setdefault(name, threading.Lock())
    with lock:
        if not os.path.isfile(target):
            partial = target + ".part"
            try:
                _write_folder_proxy(files, partial)
                os.replace(partial, target)
            finally:
                if os.path.exists(partial):
                    os.remove(partial)
    return name


def _write_folder_proxy(files: list[str], target: str) -> None:
    import av

    from PIL import Image

    fps = Fraction(FOLDER_PREVIEW_FPS)
    with Image.open(files[0]) as first:
        width, height = first.size
    scale = min(1.0, PROXY_LONG_SIDE / max(width, height))
    size = (_even(round(width * scale)), _even(round(height * scale)))

    with av.open(target, "w", format="mp4") as out:
        stream = out.add_stream("libx264", rate=fps)
        stream.width, stream.height, stream.pix_fmt = size[0], size[1], "yuv420p"
        stream.options = {"crf": "26", "preset": "veryfast"}
        stream.codec_context.time_base = 1 / fps
        for index, path in enumerate(files):
            image = open_frame(path, draft_size=size)
            frame = av.VideoFrame.from_image(fit(image, size)).reformat(format="yuv420p")
            frame.pts, frame.time_base = index, 1 / fps
            out.mux(stream.encode(frame))
        out.mux(stream.encode(None))


# ---------------------------------------------------------------- routes

def _resolve(source: str, value: str) -> str:
    import folder_paths

    if source == "input":
        path = folder_paths.get_annotated_filepath(value)
    elif source == "path":
        path = clean_path(value)
    else:
        raise ValueError("source must be input or path")
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(value)
    if not is_video_path(path):
        raise ValueError("not a video file")
    return path


def setup() -> None:
    try:
        from urllib.parse import urlencode

        from aiohttp import web
        from server import PromptServer

        routes = PromptServer.instance.routes

        @routes.get("/mhnodes/video/info")
        async def _info(request):
            query = request.rel_url.query
            source, value = query.get("source", ""), query.get("file", "")

            if source == "folder":
                folder = clean_path(value)
                try:
                    info = await asyncio.to_thread(folder_info, folder)
                    name = await asyncio.to_thread(ensure_folder_proxy, folder)
                except FileNotFoundError:
                    raise web.HTTPNotFound(reason="No such folder")
                except Exception as exc:
                    raise web.HTTPBadRequest(reason=str(exc))
                info["url"] = "/view?" + urlencode({"filename": name, "subfolder": PROXY_SUBFOLDER,
                                                   "type": "temp"})
                info["proxied"] = True
                return web.json_response(info)

            try:
                path = _resolve(source, value)
                info = await asyncio.to_thread(probe, path)
            except FileNotFoundError:
                raise web.HTTPNotFound(reason="No such video")
            except Exception as exc:
                raise web.HTTPBadRequest(reason=str(exc))

            if not info["playable"]:
                try:
                    name = await asyncio.to_thread(ensure_proxy, path)
                except Exception as exc:
                    log.error("could not build a preview proxy for %s: %s", path, exc)
                    raise web.HTTPInternalServerError(reason=f"proxy failed: {exc}")
                url = "/view?" + urlencode({"filename": name, "subfolder": PROXY_SUBFOLDER,
                                           "type": "temp"})
            elif source == "input":
                folder, name = os.path.split(value.replace("\\", "/"))
                url = "/view?" + urlencode({"filename": name, "subfolder": folder, "type": "input"})
            else:
                url = "/mhnodes/video/file?" + urlencode({"path": path})
            info["url"] = url
            info["proxied"] = not info["playable"]
            return web.json_response(info)

        @routes.get("/mhnodes/video/file")
        async def _file(request):
            # Serves a path-loader video the browser can play. Limited to video files: the node
            # can read any path anyway, but this route should not become a general file reader.
            path = clean_path(request.rel_url.query.get("path", ""))
            if not path or not is_video_path(path) or not os.path.isfile(path):
                raise web.HTTPNotFound()
            return web.FileResponse(path)

        log.info("video preview routes registered")
    except Exception as exc:
        log.error("could not register video preview routes: %s", exc)
