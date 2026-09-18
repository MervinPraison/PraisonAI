"""Image and video generation for the desktop engine."""

from __future__ import annotations

import base64
import json
import pathlib
import time
import urllib.error
import urllib.request
import uuid

OUTPUT_ROOT = "media-output"


class MediaSupervisor:
    """Generate images (OpenAI) and optional video (Replicate) from settings/env keys."""

    def __init__(self, home: pathlib.Path):
        self.home = home
        self.out = home / OUTPUT_ROOT
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "images").mkdir(exist_ok=True)
        (self.out / "videos").mkdir(exist_ok=True)

    def capabilities(self) -> dict:
        import os

        return {
            "image": True,
            "image_models": ["dall-e-3", "dall-e-2"],
            "video": bool(os.environ.get("REPLICATE_API_TOKEN") or os.environ.get("REPLICATE_API_KEY")),
            "video_hint": (
                "Set REPLICATE_API_TOKEN in ~/.praisonai/.env for video generation "
                "(Replicate models such as minimax/video-01)."
            ),
        }

    def _openai_key(self, settings: dict) -> str:
        key = str(settings.get("api_key") or "").strip()
        if key:
            return key
        import os

        return str(os.environ.get("OPENAI_API_KEY") or "").strip()

    def generate_image(
        self,
        prompt: str,
        *,
        settings: dict,
        model: str = "dall-e-3",
        size: str = "1024x1024",
    ) -> dict:
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("prompt is required")
        api_key = self._openai_key(settings)
        if not api_key:
            raise ValueError("OpenAI API key required (Settings or OPENAI_API_KEY)")

        body = json.dumps(
            {"model": model, "prompt": prompt, "n": 1, "size": size}
        ).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/images/generations",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:400]
            raise RuntimeError(detail or str(exc)) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            # DNS/connection/timeout/decode failures must surface as a structured
            # generation error, not escape and drop the local API connection.
            raise RuntimeError(f"image request failed: {exc}") from exc

        item = (payload.get("data") or [{}])[0]
        url = item.get("url")
        b64 = item.get("b64_json")
        file_id = f"img_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        local_path = self.out / "images" / f"{file_id}.png"

        try:
            if b64:
                local_path.write_bytes(base64.b64decode(b64))
            elif url:
                with urllib.request.urlopen(url, timeout=120) as img:
                    local_path.write_bytes(img.read())
            else:
                raise RuntimeError("image API returned no url or b64_json")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"image download failed: {exc}") from exc

        raw = local_path.read_bytes()
        data_url = "data:image/png;base64," + base64.b64encode(raw).decode()

        return {
            "id": file_id,
            "path": str(local_path),
            "url": url,
            "data_url": data_url,
            "model": model,
            "prompt": prompt,
        }

    def generate_video(self, prompt: str, *, settings: dict) -> dict:  # noqa: ARG002
        import os

        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("prompt is required")
        token = os.environ.get("REPLICATE_API_TOKEN") or os.environ.get("REPLICATE_API_KEY")
        if not token:
            raise ValueError(
                "Video generation needs REPLICATE_API_TOKEN in ~/.praisonai/.env"
            )

        body = json.dumps({"input": {"prompt": prompt}}).encode()
        create = urllib.request.Request(
            "https://api.replicate.com/v1/models/minimax/video-01/predictions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Prefer": "wait=120",
            },
        )
        try:
            with urllib.request.urlopen(create, timeout=180) as resp:
                pred = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:400]
            raise RuntimeError(detail or str(exc)) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise RuntimeError(f"video request failed: {exc}") from exc

        output = pred.get("output")
        if isinstance(output, list):
            output = output[0] if output else None
        if not output:
            raise RuntimeError(pred.get("error") or "video generation produced no output")

        file_id = f"vid_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        local_path = self.out / "videos" / f"{file_id}.mp4"
        try:
            with urllib.request.urlopen(str(output), timeout=300) as vid:
                local_path.write_bytes(vid.read())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"video download failed: {exc}") from exc

        return {
            "id": file_id,
            "path": str(local_path),
            "url": str(output),
            "prompt": prompt,
        }

    def list_recent(self, kind: str, *, limit: int = 12) -> list[dict]:
        sub = "images" if kind == "image" else "videos"
        folder = self.out / sub
        if not folder.is_dir():
            return []
        files = sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        out: list[dict] = []
        for fp in files[:limit]:
            out.append(
                {
                    "name": fp.name,
                    "path": str(fp),
                    "modified": int(fp.stat().st_mtime),
                }
            )
        return out
