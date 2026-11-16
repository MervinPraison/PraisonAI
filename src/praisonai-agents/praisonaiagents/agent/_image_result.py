"""Savable wrapper for ImageAgent responses (keeps the raw response API intact)."""
import base64
from typing import Any, List

_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024


class ImageResult:
    """Wraps a provider image response and adds ``save()``.

    Attribute and item access fall through to the wrapped response, so
    ``result.data[0].b64_json`` and ``result["data"]`` keep working.
    """

    def __init__(self, response: Any):
        self._response = response

    def __getattr__(self, name: str) -> Any:
        if "_response" not in self.__dict__:
            raise AttributeError(name)
        return getattr(self.__dict__["_response"], name)

    def __getitem__(self, key: Any) -> Any:
        return self._response[key]

    def __contains__(self, key: Any) -> bool:
        return key in self._response

    def __iter__(self):
        return iter(self._response)

    def __repr__(self) -> str:
        return f"ImageResult({self._response!r})"

    @property
    def images(self) -> List[Any]:
        """List of image objects returned by the provider (one per ``n``)."""
        data = self._response.get("data") if isinstance(self._response, dict) else getattr(self._response, "data", None)
        return list(data or [])

    def save(self, path: str, index: int = 0) -> str:
        """Write image ``index`` to ``path`` (base64 is decoded, http(s) URLs are downloaded)."""
        images = self.images
        if not images:
            raise ValueError("No image data in response")
        image = images[index]
        get = image.get if isinstance(image, dict) else (lambda k: getattr(image, k, None))
        b64, url = get("b64_json"), get("url")
        if b64:
            data = base64.b64decode(b64)
        elif url:
            data = _download(url)
        else:
            raise ValueError("Image has neither b64_json nor url")
        with open(path, "wb") as f:
            f.write(data)
        return path


def _download(url: str) -> bytes:
    import urllib.request

    if not url.startswith(("https://", "http://")):
        raise ValueError("Image URL must be http(s)")
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 - scheme checked above
        data = resp.read(_MAX_DOWNLOAD_BYTES + 1)
    if len(data) > _MAX_DOWNLOAD_BYTES:
        raise ValueError("Image exceeds maximum download size")
    return data
