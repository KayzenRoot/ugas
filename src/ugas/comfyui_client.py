"""Small dependency-free HTTP client for the ComfyUI server API."""

from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


class ComfyUIError(RuntimeError):
    """Base class for safe, structured ComfyUI failures."""


class ComfyUIHTTPError(ComfyUIError):
    def __init__(self, method: str, path: str, status: int, message: str):
        super().__init__(f"ComfyUI {method} {path} failed with HTTP {status}: {message[:240]}")
        self.method = method
        self.path = path
        self.status = status


class ComfyUIProtocolError(ComfyUIError):
    pass


class ComfyUITimeoutError(ComfyUIError):
    pass


class ComfyUIExecutionError(ComfyUIError):
    pass


@dataclass(frozen=True)
class ComfyUIClient:
    base_url: str = "http://127.0.0.1:8188"
    timeout: float = 10.0
    max_json_bytes: int = 32 * 1024 * 1024
    max_output_bytes: int = 128 * 1024 * 1024

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    def _url(self, path: str, query: Mapping[str, object] | None = None) -> str:
        url = f"{self.base_url}/{path.lstrip('/')}"
        if query:
            encoded = urllib.parse.urlencode({key: value for key, value in query.items() if value is not None})
            if encoded:
                url += "?" + encoded
        return url

    @staticmethod
    def _safe_error_body(data: bytes) -> str:
        text = data.decode("utf-8", errors="replace").replace("\r", " ").replace("\n", " ")
        return text[:240] or "empty response"

    def _request_bytes(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, object] | None = None,
        body: bytes | None = None,
        content_type: str | None = None,
        max_bytes: int | None = None,
    ) -> bytes:
        headers = {"Accept": "application/json, image/png, application/octet-stream"}
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(self._url(path, query), data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                limit = max_bytes or self.max_json_bytes
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(min(1024 * 1024, limit - total + 1))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > limit:
                        raise ComfyUIProtocolError(f"ComfyUI response exceeded {limit} bytes")
                return b"".join(chunks)
        except urllib.error.HTTPError as exc:
            body_bytes = exc.read(4096)
            raise ComfyUIHTTPError(method, path, exc.code, self._safe_error_body(body_bytes)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, TimeoutError) or "timed out" in str(reason).casefold():
                raise ComfyUITimeoutError(f"ComfyUI {method} {path} timed out") from exc
            raise ComfyUIError(f"ComfyUI {method} {path} unavailable: {str(reason)[:240]}") from exc

    def _json(self, method: str, path: str, *, query: Mapping[str, object] | None = None, payload: Any = None) -> Any:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        raw = self._request_bytes(method, path, query=query, body=body, content_type="application/json" if body else None)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ComfyUIProtocolError(f"ComfyUI {method} {path} returned invalid JSON") from exc

    def health(self) -> dict[str, Any]:
        value = self._json("GET", "/system_stats")
        if not isinstance(value, dict):
            raise ComfyUIProtocolError("/system_stats must return an object")
        return value

    def safe_health(self) -> dict[str, Any]:
        try:
            return {"status": "healthy", "value": self.health()}
        except ComfyUIError as exc:
            return {"status": "unavailable", "error": str(exc), "error_type": type(exc).__name__}

    def safe_call(self, method, *args, **kwargs) -> dict[str, Any]:
        try:
            return {"status": "ok", "value": method(*args, **kwargs)}
        except ComfyUIError as exc:
            return {"status": "error", "error": str(exc), "error_type": type(exc).__name__}

    def features(self) -> dict[str, Any]:
        value = self._json("GET", "/features")
        if not isinstance(value, dict):
            raise ComfyUIProtocolError("/features must return an object")
        return value

    def list_model_types(self) -> list[str]:
        value = self._json("GET", "/models")
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
        if isinstance(value, dict):
            return [str(key) for key in value]
        raise ComfyUIProtocolError("/models must return a list or object")

    def list_models(self, folder: str) -> list[str]:
        safe_folder = urllib.parse.quote(folder.strip("/"), safe="")
        value = self._json("GET", f"/models/{safe_folder}")
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
        if isinstance(value, dict):
            items = value.get("models", value.get("files", value))
            if isinstance(items, list):
                return [str(item) for item in items]
        raise ComfyUIProtocolError(f"/models/{folder} must return a model list")

    def node_info(self, node_class: str | None = None) -> dict[str, Any]:
        path = "/object_info" if node_class is None else f"/object_info/{urllib.parse.quote(node_class, safe='')}"
        value = self._json("GET", path)
        if not isinstance(value, dict):
            raise ComfyUIProtocolError(f"{path} must return an object")
        return value

    def submit_workflow(self, workflow: Mapping[str, Any], client_id: str | None = None) -> dict[str, Any]:
        if not isinstance(workflow, Mapping) or not workflow:
            raise ValueError("workflow must be a non-empty API-format mapping")
        payload: dict[str, Any] = {"prompt": dict(workflow), "client_id": client_id or str(uuid.uuid4())}
        value = self._json("POST", "/prompt", payload=payload)
        if not isinstance(value, dict):
            raise ComfyUIProtocolError("/prompt response must be an object")
        if value.get("error") or value.get("node_errors"):
            raise ComfyUIExecutionError(json.dumps({"error": value.get("error"), "node_errors": value.get("node_errors")}, ensure_ascii=False))
        prompt_id = value.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ComfyUIProtocolError("/prompt response did not contain prompt_id")
        return value

    def queue_status(self) -> dict[str, Any]:
        value = self._json("GET", "/prompt")
        if not isinstance(value, dict):
            raise ComfyUIProtocolError("/prompt GET response must be an object")
        return value

    def free_memory(self, *, unload_models: bool = True, free_memory: bool = True) -> dict[str, Any]:
        """Ask ComfyUI to unload models between bounded qualification jobs."""
        value = self._json("POST", "/free", payload={"unload_models": unload_models, "free_memory": free_memory})
        if not isinstance(value, dict):
            raise ComfyUIProtocolError("/free response must be an object")
        return value

    def history(self, prompt_id: str) -> dict[str, Any]:
        value = self._json("GET", f"/history/{urllib.parse.quote(prompt_id, safe='')}")
        if not isinstance(value, dict):
            raise ComfyUIProtocolError("/history response must be an object")
        return value

    def fetch_output(
        self,
        filename: str,
        *,
        subfolder: str = "",
        output_type: str = "output",
    ) -> bytes:
        return self._request_bytes(
            "GET",
            "/view",
            query={"filename": filename, "subfolder": subfolder, "type": output_type},
            max_bytes=self.max_output_bytes,
        )

    def fetch_history_outputs(self, history_item: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Retrieve only image outputs described by a completed history item."""
        outputs: list[dict[str, Any]] = []
        for node_id, node_output in (history_item.get("outputs") or {}).items():
            if not isinstance(node_output, Mapping):
                continue
            for image in node_output.get("images", []):
                if not isinstance(image, Mapping) or not isinstance(image.get("filename"), str):
                    continue
                data = self.fetch_output(str(image["filename"]), subfolder=str(image.get("subfolder", "")), output_type=str(image.get("type", "output")))
                outputs.append({"node_id": node_id, "filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image.get("type", "output"), "data": data})
        return outputs

    def upload_image(self, image_path: Path, *, overwrite: bool = True, image_type: str = "input") -> dict[str, Any]:
        """Upload a reference image using ComfyUI's multipart endpoint."""
        image_path = image_path.resolve()
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        boundary = f"----ugas-{uuid.uuid4().hex}"
        file_bytes = image_path.read_bytes()
        safe_name = image_path.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{safe_name}\"\r\nContent-Type: {content_type}\r\n\r\n".encode(),
            file_bytes,
            f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\n{str(overwrite).lower()}\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\n{image_type}\r\n".encode(),
            f"--{boundary}--\r\n".encode(),
        ]
        raw = self._request_bytes(
            "POST",
            "/upload/image",
            body=b"".join(parts),
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ComfyUIProtocolError("/upload/image returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise ComfyUIProtocolError("/upload/image response must be an object")
        return value

    def poll_history(
        self,
        prompt_id: str,
        *,
        timeout: float = 300.0,
        initial_interval: float = 0.5,
        max_interval: float = 5.0,
        on_poll: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        interval = max(0.05, initial_interval)
        while True:
            if on_poll is not None:
                on_poll(prompt_id)
            history = self.history(prompt_id)
            item = history.get(prompt_id)
            if isinstance(item, dict):
                status = item.get("status")
                if isinstance(status, dict) and status.get("status_str") in {"error", "failed"}:
                    raise ComfyUIExecutionError(f"ComfyUI job {prompt_id} failed: {status.get('status_str')}")
                if "outputs" in item or (isinstance(status, dict) and status.get("completed") is True):
                    bound = dict(item)
                    bound["_ugas_prompt_id"] = prompt_id
                    return bound
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ComfyUITimeoutError(f"ComfyUI job {prompt_id} exceeded polling timeout")
            time.sleep(min(interval, remaining))
            interval = min(max_interval, interval * 1.7)
