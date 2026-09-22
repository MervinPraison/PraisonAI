"""Creative Studio — Flow-like projects for image/video generation.

Persists under DATA_DIR/studio/. Video jobs run in background threads and call
praisonaiagents VideoAgent when LiteLLM is available.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

DEFAULT_MODELS = [
    {"id": "openai/sora-2", "label": "OpenAI Sora 2", "provider": "openai"},
    {"id": "openai/sora-2-pro", "label": "OpenAI Sora 2 Pro", "provider": "openai"},
    {
        "id": "gemini/veo-3.1-generate-preview",
        "label": "Gemini Veo 3.1",
        "provider": "google",
    },
    {
        "id": "gemini/veo-3.1-fast-generate-preview",
        "label": "Gemini Veo 3.1 Fast",
        "provider": "google",
    },
    {"id": "runwayml/gen4_turbo", "label": "Runway Gen-4 Turbo", "provider": "runway"},
]

# Default for Studio image tests — Flare is latest; use quality=low + small size to limit spend.
DEFAULT_IMAGE_MODEL = "openai/gpt-image-2.5-flare-2026-09-08"

IMAGE_MODELS = [
    {
        "id": DEFAULT_IMAGE_MODEL,
        "label": "GPT-Image 2.5 Flare (2026-09-08) — recommended for tests",
        "provider": "openai",
    },
    {
        "id": "openai/gpt-image-2.5-flare",
        "label": "GPT-Image 2.5 Flare (alias)",
        "provider": "openai",
    },
    {"id": "openai/dall-e-3", "label": "DALL·E 3", "provider": "openai"},
    {"id": "openai/dall-e-2", "label": "DALL·E 2", "provider": "openai"},
]

# Billing note shown in API + UI: frequent Flare calls burn through prepaid credit fast.
IMAGE_COST_NOTICE = (
    "gpt-image-2.5-flare (including gpt-image-2.5-flare-2026-09-08) accrues cost per "
    "image; regular production use will deplete API balance quickly. For testing, "
    "use quality=low, size=1024x1024, and n_variants=1."
)

LOW_COST_IMAGE_DEFAULTS = {
    "quality": "low",
    "size": "1024x1024",
}

MAX_CONCURRENT_JOBS = 2


def _patch_headless_rich() -> None:
    """Rich Progress breaks in the desktop engine subprocess on Windows (OSError 22)."""
    if not sys.platform.startswith("win"):
        return
    try:
        import rich.progress as rp

        class _HeadlessProgress:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def add_task(self, *args, **kwargs):
                return 0

            def update(self, *args, **kwargs):
                pass

        rp.Progress = _HeadlessProgress  # type: ignore[misc, assignment]
    except Exception:
        pass


_patch_headless_rich()


def _now() -> float:
    return time.time()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class StudioJob:
    id: str
    project_id: str
    kind: str  # video | image
    model: str
    prompt: str
    status: str = "queued"  # queued | running | completed | failed
    error: Optional[str] = None
    asset_ids: List[str] = field(default_factory=list)
    image_quality: Optional[str] = None
    image_size: Optional[str] = None
    created_at: float = field(default_factory=_now)
    finished_at: Optional[float] = None

    def summary(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "kind": self.kind,
            "model": self.model,
            "prompt": self.prompt,
            "status": self.status,
            "error": self.error,
            "asset_ids": self.asset_ids,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


def build_image_kwargs(
    model: str,
    quality: Optional[str] = None,
    size: Optional[str] = None,
) -> Dict[str, Any]:
    """Map Studio UI options to LiteLLM / OpenAI image_generation params."""
    q = (quality or LOW_COST_IMAGE_DEFAULTS["quality"]).strip().lower()
    sz = size or LOW_COST_IMAGE_DEFAULTS["size"]
    model_l = model.lower()
    params: Dict[str, Any] = {"n": 1, "size": sz}
    if "gpt-image" in model_l:
        if q in ("low", "medium", "high"):
            params["quality"] = q
        else:
            params["quality"] = "low"
    elif "dall-e-3" in model_l:
        params["quality"] = "standard" if q == "low" else ("hd" if q == "high" else "standard")
    return params


def _normalize_image_response(result: Any) -> Dict[str, Any]:
    """LiteLLM may return a dict or a pydantic/OpenAI-style object."""
    if isinstance(result, dict):
        return result
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if hasattr(result, "dict"):
        return result.dict()
    data = getattr(result, "data", None)
    if data is not None:
        items: List[Dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict):
                items.append(item)
            else:
                items.append(
                    {
                        "url": getattr(item, "url", None),
                        "b64_json": getattr(item, "b64_json", None),
                    }
                )
        return {"data": items}
    raise RuntimeError("unexpected image generation response shape")


def _generate_image_litellm(model: str, prompt: str, img_kw: Dict[str, Any]) -> Dict[str, Any]:
    """Headless image generation — avoids ImageAgent's Rich spinner (OSError 22 on Windows)."""
    _patch_headless_rich()
    try:
        from litellm import image_generation
    except ImportError as exc:
        raise RuntimeError("litellm is required for studio image generation") from exc
    return _normalize_image_response(
        image_generation(
            model=model,
            prompt=prompt,
            drop_params=True,
            response_format="b64_json",
            **img_kw,
        )
    )


def _video_field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _generate_video_litellm(
    model: str,
    prompt: str,
    seconds: str,
    ref_path: Optional[str] = None,
    poll_interval: int = 10,
    max_wait: int = 600,
) -> bytes:
    """Headless video generation (no VideoAgent Rich UI)."""
    try:
        from litellm.videos import video_content, video_generation, video_status
    except ImportError as exc:
        raise RuntimeError("litellm video support is required for studio video") from exc

    params: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "seconds": str(seconds),
    }
    if ref_path:
        params["input_reference"] = ref_path
    created = video_generation(**params)
    video_id = _video_field(created, "id")
    if not video_id:
        raise RuntimeError("video generation returned no id")

    start = time.time()
    while time.time() - start < max_wait:
        st = video_status(video_id=video_id)
        status = _video_field(st, "status", "")
        if status == "completed":
            return video_content(video_id=video_id)
        if status == "failed":
            err = _video_field(st, "error") or "video generation failed"
            raise RuntimeError(str(err))
        time.sleep(poll_interval)
    raise TimeoutError(f"video did not complete within {max_wait}s")


class StudioManager:
    def __init__(self, data_dir: Path, log_fn: Optional[Callable[[str], None]] = None):
        self.root = data_dir / "studio"
        self.root.mkdir(parents=True, exist_ok=True)
        self._log = log_fn or (lambda _msg: None)
        self._lock = threading.Lock()
        self._jobs: Dict[str, StudioJob] = {}
        self._active = 0

    def models(self) -> Dict[str, Any]:
        return {
            "video": DEFAULT_MODELS,
            "image": IMAGE_MODELS,
            "image_defaults": {
                "model": DEFAULT_IMAGE_MODEL,
                **LOW_COST_IMAGE_DEFAULTS,
            },
            "image_cost_notice": IMAGE_COST_NOTICE,
        }

    def list_projects(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for path in sorted(self.root.glob("*/project.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                out.append(
                    {
                        "id": data["id"],
                        "name": data.get("name", "Untitled"),
                        "updated_at": data.get("updated_at", 0),
                        "asset_count": len(data.get("assets", [])),
                    }
                )
            except (json.JSONDecodeError, KeyError, OSError):
                continue
        out.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        return out

    def _project_dir(self, project_id: str) -> Path:
        d = self.root / project_id
        if not d.is_dir():
            raise ValueError("no such project")
        return d

    def _load_project(self, project_id: str) -> Dict[str, Any]:
        path = self._project_dir(project_id) / "project.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_project(self, project: Dict[str, Any]) -> None:
        project["updated_at"] = _now()
        path = self._project_dir(project["id"]) / "project.json"
        path.write_text(json.dumps(project, indent=2), encoding="utf-8")

    def create_project(self, name: str) -> Dict[str, Any]:
        name = (name or "Untitled project").strip()[:120]
        pid = _new_id("proj")
        pdir = self.root / pid
        (pdir / "assets").mkdir(parents=True, exist_ok=True)
        (pdir / "outputs").mkdir(parents=True, exist_ok=True)
        project = {
            "id": pid,
            "name": name,
            "created_at": _now(),
            "updated_at": _now(),
            "assets": [],
            "timeline": [],
        }
        self._save_project(project)
        return project

    def get_project(self, project_id: str) -> Dict[str, Any]:
        project = self._load_project(project_id)
        assets = []
        for a in project.get("assets", []):
            entry = dict(a)
            path = self._project_dir(project_id) / a.get("path", "")
            entry["exists"] = path.is_file()
            assets.append(entry)
        project["assets"] = assets
        return project

    def add_image_asset(
        self, project_id: str, filename: str, data_base64: str, prompt: str = ""
    ) -> Dict[str, Any]:
        project = self._load_project(project_id)
        raw = data_base64.split(",", 1)[-1]
        try:
            blob = base64.b64decode(raw, validate=True)
        except Exception as exc:
            raise ValueError(f"invalid image data: {exc}") from exc
        if len(blob) > 20 * 1024 * 1024:
            raise ValueError("image exceeds 20 MB limit")
        safe = "".join(c for c in filename if c.isalnum() or c in "._-") or "upload.png"
        aid = _new_id("asset")
        rel = f"assets/{aid}_{safe}"
        out = self._project_dir(project_id) / rel
        out.write_bytes(blob)
        asset = {
            "id": aid,
            "type": "image",
            "path": rel,
            "prompt": prompt,
            "created_at": _now(),
        }
        project.setdefault("assets", []).append(asset)
        self._save_project(project)
        return asset

    def set_timeline(self, project_id: str, asset_ids: List[str]) -> Dict[str, Any]:
        project = self._load_project(project_id)
        known = {a["id"] for a in project.get("assets", []) if a.get("type") == "video"}
        timeline = [i for i in asset_ids if i in known]
        project["timeline"] = timeline
        self._save_project(project)
        return {"timeline": timeline}

    def get_job(self, job_id: str) -> Optional[StudioJob]:
        with self._lock:
            job = self._jobs.get(job_id)
            return job

    def start_generate(
        self,
        project_id: str,
        *,
        kind: str,
        model: str,
        prompt: str,
        seconds: str = "8",
        ref_asset_id: Optional[str] = None,
        n_variants: int = 1,
        image_quality: Optional[str] = None,
        image_size: Optional[str] = None,
    ) -> List[StudioJob]:
        if kind not in ("video", "image"):
            raise ValueError("kind must be video or image")
        if not model or not prompt.strip():
            raise ValueError("model and prompt are required")
        n_variants = max(1, min(int(n_variants), 4))
        self._load_project(project_id)  # validate exists

        jobs: List[StudioJob] = []
        for _ in range(n_variants):
            jid = _new_id("job")
            job = StudioJob(
                id=jid,
                project_id=project_id,
                kind=kind,
                model=model.strip(),
                prompt=prompt.strip(),
                image_quality=image_quality,
                image_size=image_size,
            )
            with self._lock:
                self._jobs[jid] = job
            jobs.append(job)
            threading.Thread(
                target=self._run_job,
                args=(job, seconds, ref_asset_id),
                daemon=True,
                name=f"studio-{jid}",
            ).start()
        return jobs

    def _acquire_slot(self) -> None:
        while True:
            with self._lock:
                if self._active < MAX_CONCURRENT_JOBS:
                    self._active += 1
                    return
            time.sleep(0.25)

    def _release_slot(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)

    def _run_job(self, job: StudioJob, seconds: str, ref_asset_id: Optional[str]) -> None:
        _patch_headless_rich()
        self._acquire_slot()
        job.status = "running"
        try:
            if job.kind == "video":
                asset = self._generate_video(job, seconds, ref_asset_id)
            else:
                asset = self._generate_image(job)
            job.asset_ids = [asset["id"]]
            job.status = "completed"
            job.finished_at = _now()
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = _now()
            self._log(f"studio job {job.id} failed: {exc}")
        finally:
            self._release_slot()

    def _generate_video(
        self, job: StudioJob, seconds: str, ref_asset_id: Optional[str]
    ) -> Dict[str, Any]:
        ref_path = None
        if ref_asset_id:
            project = self._load_project(job.project_id)
            for a in project.get("assets", []):
                if a["id"] == ref_asset_id and a.get("type") == "image":
                    ref_path = str(self._project_dir(job.project_id) / a["path"])
                    break

        blob = _generate_video_litellm(
            job.model,
            job.prompt,
            str(seconds),
            ref_path=ref_path,
        )

        aid = _new_id("asset")
        rel = f"outputs/{aid}.mp4"
        out = self._project_dir(job.project_id) / rel
        out.write_bytes(blob)

        project = self._load_project(job.project_id)
        asset = {
            "id": aid,
            "type": "video",
            "path": rel,
            "prompt": job.prompt,
            "model": job.model,
            "job_id": job.id,
            "created_at": _now(),
        }
        project.setdefault("assets", []).append(asset)
        project.setdefault("timeline", []).append(aid)
        self._save_project(project)
        return asset

    def _generate_image(self, job: StudioJob) -> Dict[str, Any]:
        model = job.model
        if not model.startswith("openai/") and "dall-e" not in model and "gpt-image" not in model:
            model = f"openai/{model}"
        img_kw = build_image_kwargs(
            model, quality=job.image_quality, size=job.image_size
        )
        result = _generate_image_litellm(model, job.prompt, img_kw)
        data = result.get("data") or []
        if not data or not isinstance(data[0], dict):
            raise RuntimeError("image generation returned no url or bytes")
        first = data[0]
        b64 = first.get("b64_json")
        url = first.get("url")
        aid = _new_id("asset")
        rel = f"assets/{aid}.png"
        out = self._project_dir(job.project_id) / rel
        if b64:
            out.write_bytes(base64.b64decode(b64))
            return self._register_image_asset(job, aid, rel)
        if not url:
            raise RuntimeError("image generation returned no url or bytes")
        import urllib.request

        with urllib.request.urlopen(url, timeout=120) as resp:
            out.write_bytes(resp.read())
        return self._register_image_asset(job, aid, rel)

    def _register_image_asset(self, job: StudioJob, aid: str, rel: str) -> Dict[str, Any]:
        project = self._load_project(job.project_id)
        asset = {
            "id": aid,
            "type": "image",
            "path": rel,
            "prompt": job.prompt,
            "model": job.model,
            "job_id": job.id,
            "created_at": _now(),
        }
        project.setdefault("assets", []).append(asset)
        self._save_project(project)
        return asset

    def asset_file(self, project_id: str, asset_id: str) -> tuple[Path, str]:
        project = self._load_project(project_id)
        for a in project.get("assets", []):
            if a["id"] == asset_id:
                path = self._project_dir(project_id) / a["path"]
                if not path.is_file():
                    raise ValueError("asset file missing")
                ext = path.suffix.lower()
                mime = {
                    ".mp4": "video/mp4",
                    ".webm": "video/webm",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                }.get(ext, "application/octet-stream")
                return path, mime
        raise ValueError("no such asset")

    def export_timeline(self, project_id: str, output_name: str = "export.mp4") -> Dict[str, Any]:
        project = self._load_project(project_id)
        timeline = project.get("timeline") or []
        if not timeline:
            raise ValueError("timeline is empty")
        assets = {a["id"]: a for a in project.get("assets", [])}
        clips: List[Path] = []
        for aid in timeline:
            a = assets.get(aid)
            if not a or a.get("type") != "video":
                continue
            p = self._project_dir(project_id) / a["path"]
            if p.is_file():
                clips.append(p)
        if not clips:
            raise ValueError("no video clips on timeline")

        safe = "".join(c for c in output_name if c.isalnum() or c in "._-") or "export.mp4"
        if not safe.endswith(".mp4"):
            safe += ".mp4"
        out = self._project_dir(project_id) / "outputs" / safe
        out.parent.mkdir(parents=True, exist_ok=True)

        if len(clips) == 1:
            shutil.copy2(clips[0], out)
        else:
            self._ffmpeg_concat(clips, out)

        rel = f"outputs/{safe}"
        export_asset = {
            "id": _new_id("asset"),
            "type": "export",
            "path": rel,
            "created_at": _now(),
        }
        project.setdefault("assets", []).append(export_asset)
        self._save_project(project)
        return {"path": str(out), "asset": export_asset}

    def _ffmpeg_concat(self, clips: List[Path], out: Path) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError(
                "ffmpeg not found — install ffmpeg or export a single clip only"
            )
        list_file = out.parent / f".concat_{uuid.uuid4().hex[:8]}.txt"
        try:
            lines = [f"file '{c.resolve().as_posix()}'" for c in clips]
            list_file.write_text("\n".join(lines), encoding="utf-8")
            cmd = [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                str(out),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr[-500:] or "ffmpeg concat failed")
        finally:
            list_file.unlink(missing_ok=True)


def credential_hints() -> Dict[str, Any]:
    """Env vars the UI should mention for studio generation."""
    return {
        "openai": {
            "env": ["OPENAI_API_KEY"],
            "models": [
                "openai/sora-2",
                "openai/sora-2-pro",
                DEFAULT_IMAGE_MODEL,
                "openai/dall-e-3",
            ],
            "url": "https://platform.openai.com/api-keys",
            "billing_note": IMAGE_COST_NOTICE,
        },
        "google": {
            "env": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
            "models": ["gemini/veo-3.1-generate-preview"],
            "url": "https://aistudio.google.com/app/apikey",
        },
        "runway": {
            "env": ["RUNWAYML_API_SECRET"],
            "models": ["runwayml/gen4_turbo"],
            "url": "https://docs.dev.runwayml.com/",
        },
        "vertex": {
            "env": ["GOOGLE_APPLICATION_CREDENTIALS", "VERTEXAI_PROJECT"],
            "models": ["vertex_ai/veo-3.1-generate-001"],
            "url": "https://cloud.google.com/vertex-ai",
        },
        "azure_openai": {
            "env": ["AZURE_API_KEY", "AZURE_API_BASE"],
            "models": ["azure/sora-2"],
            "url": "https://portal.azure.com/",
        },
    }
