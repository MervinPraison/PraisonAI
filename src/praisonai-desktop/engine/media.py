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

# Video model catalog. Each entry declares the env key that unlocks it, so the
# desktop can show a model picker instead of the old hardcoded Replicate path.
# Replicate stays a preset (not the sole path); SDK providers route through
# praisonaiagents.VideoAgent, so the engine never reimplements provider HTTP.
VIDEO_MODELS = [
    {
        "id": "replicate/minimax/video-01",
        "display_name": "MiniMax video-01 (Replicate)",
        "provider": "replicate",
        "env": ("REPLICATE_API_TOKEN", "REPLICATE_API_KEY"),
    },
    {
        "id": "openai/sora-2",
        "display_name": "OpenAI Sora 2",
        "provider": "openai",
        "env": ("OPENAI_API_KEY",),
    },
    {
        "id": "gemini/veo-3.1-lite-generate-preview",
        "display_name": "Google Veo 3.1 Lite",
        "provider": "gemini",
        "env": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    },
    {
        "id": "gemini/veo-3.1-generate-preview",
        "display_name": "Google Veo 3.1",
        "provider": "gemini",
        "env": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    },
]


class MediaSupervisor:
    """Generate images (OpenAI) and optional video (Replicate) from settings/env keys."""

    def __init__(self, home: pathlib.Path):
        self.home = home
        self.out = home / OUTPUT_ROOT
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "images").mkdir(exist_ok=True)
        (self.out / "videos").mkdir(exist_ok=True)

    def list_video_models(self) -> list[dict]:
        """Catalog of video models with `configured` set from available env keys."""
        import os

        models = []
        for m in VIDEO_MODELS:
            models.append(
                {
                    "id": m["id"],
                    "display_name": m["display_name"],
                    "provider": m["provider"],
                    "configured": any(os.environ.get(k) for k in m["env"]),
                }
            )
        return models

    def capabilities(self) -> dict:
        import os

        return {
            "image": True,
            "image_models": ["dall-e-3", "dall-e-2"],
            "video": bool(os.environ.get("REPLICATE_API_TOKEN") or os.environ.get("REPLICATE_API_KEY")),
            "video_models": self.list_video_models(),
            "video_hint": (
                "Set a provider key in ~/.praisonai/.env for video generation "
                "(REPLICATE_API_TOKEN for MiniMax, OPENAI_API_KEY for Sora, "
                "GEMINI_API_KEY for Veo)."
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

        item = (payload.get("data") or [{}])[0]
        url = item.get("url")
        b64 = item.get("b64_json")
        file_id = f"img_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        local_path = self.out / "images" / f"{file_id}.png"

        if b64:
            local_path.write_bytes(base64.b64decode(b64))
        elif url:
            with urllib.request.urlopen(url, timeout=120) as img:
                local_path.write_bytes(img.read())
        else:
            raise RuntimeError("image API returned no url or b64_json")

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

    def generate_video(
        self,
        prompt: str,
        *,
        settings: dict,  # noqa: ARG002
        model: str = "replicate/minimax/video-01",
    ) -> dict:
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("prompt is required")
        model = (model or "replicate/minimax/video-01").strip()
        known = {m["id"] for m in VIDEO_MODELS}
        if model not in known:
            raise ValueError(
                f"Unknown video model {model!r}. Choose one of: {', '.join(sorted(known))}"
            )
        if model == "replicate/minimax/video-01":
            return self._generate_video_replicate(prompt)
        return self._generate_video_sdk(prompt, model=model)

    def _generate_video_sdk(self, prompt: str, *, model: str) -> dict:
        """Route SDK-capable providers (Sora, Veo) through VideoAgent so the
        engine never reimplements provider HTTP."""
        try:
            from praisonaiagents import VideoAgent
        except ImportError as exc:
            raise RuntimeError(
                "praisonaiagents with litellm is required for this provider. "
                "Install with: pip install 'praisonaiagents[llm]'"
            ) from exc

        file_id = f"vid_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        local_path = self.out / "videos" / f"{file_id}.mp4"
        try:
            agent = VideoAgent(llm=model, verbose=False)
            # On success start() returns the video bytes and writes `output`.
            # On a failed/incomplete generation it returns the status object
            # WITHOUT writing the file, so we must inspect the result and the
            # file before reporting success — otherwise a failed job would show
            # a "saved" notification pointing at a nonexistent path.
            result = agent.start(prompt, wait=True, output=str(local_path))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(str(exc)) from exc

        if not isinstance(result, (bytes, bytearray)):
            status = getattr(result, "status", "failed")
            raise RuntimeError(
                f"Video generation did not complete (status: {status})"
            )
        if not local_path.is_file() or local_path.stat().st_size == 0:
            raise RuntimeError("Video generation reported success but wrote no file")

        return {
            "id": file_id,
            "path": str(local_path),
            "url": None,
            "model": model,
            "prompt": prompt,
        }

    def _generate_video_replicate(self, prompt: str) -> dict:
        import os

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

        output = pred.get("output")
        if isinstance(output, list):
            output = output[0] if output else None
        if not output:
            raise RuntimeError(pred.get("error") or "video generation produced no output")

        file_id = f"vid_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        local_path = self.out / "videos" / f"{file_id}.mp4"
        with urllib.request.urlopen(str(output), timeout=300) as vid:
            local_path.write_bytes(vid.read())

        return {
            "id": file_id,
            "path": str(local_path),
            "url": str(output),
            "model": "replicate/minimax/video-01",
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
