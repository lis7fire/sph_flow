from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import parse

from sph_flow.service import CaptureScheduler, MonitorService


class MonitorHttpServer:
    def __init__(self, service: MonitorService, scheduler: CaptureScheduler, web_dir: Path) -> None:
        self.service = service
        self.scheduler = scheduler
        self.web_dir = web_dir

    def serve_forever(self) -> None:
        settings = self.service.get_settings()
        server = ThreadingHTTPServer((settings.listen_host, settings.listen_port), self._build_handler())
        print(f"视频号流速监控系统已启动：http://{settings.listen_host}:{settings.listen_port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            self.scheduler.stop()

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        service = self.service
        scheduler = self.scheduler
        web_dir = self.web_dir

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = parse.urlparse(self.path)
                try:
                    if parsed.path in {"/", "/index.html"}:
                        self._serve_file(web_dir / "index.html", "text/html; charset=utf-8")
                        return
                    if parsed.path in {"/app.js", "/styles.css"}:
                        content_type, _ = mimetypes.guess_type(parsed.path)
                        self._serve_file(web_dir / parsed.path.lstrip("/"), content_type or "text/plain; charset=utf-8")
                        return
                    if parsed.path == "/api/bootstrap":
                        self._write_json(HTTPStatus.OK, service.get_status_bundle())
                        return
                    if parsed.path == "/api/window-stats":
                        query = parse.parse_qs(parsed.query)
                        window_minutes = int((query.get("windowMinutes") or ["5"])[0] or 5)
                        self._write_json(HTTPStatus.OK, service.list_window_stats(window_minutes))
                        return
                    if parsed.path == "/api/trend":
                        query = parse.parse_qs(parsed.query)
                        video_id = (query.get("videoId") or [""])[0]
                        metric = (query.get("metric") or ["playCount"])[0]
                        window_minutes = int((query.get("windowMinutes") or ["1"])[0] or 1)
                        self._write_json(HTTPStatus.OK, service.build_trend_points(video_id, metric, window_minutes))
                        return
                    if parsed.path == "/api/export.xlsx":
                        payload = service.export_snapshots_xlsx()
                        self.send_response(HTTPStatus.OK)
                        self.send_header(
                            "Content-Type",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                        self.send_header("Content-Disposition", 'attachment; filename="video-stats.xlsx"')
                        self.send_header("Content-Length", str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                        return
                    self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})
                except Exception as exc:  # noqa: BLE001
                    self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})

            def do_POST(self) -> None:  # noqa: N802
                parsed = parse.urlparse(self.path)
                payload = self._read_json()
                try:
                    if parsed.path == "/api/settings":
                        settings = service.save_settings(
                            {
                                "poll_interval_minutes": payload.get("pollIntervalMinutes"),
                                "default_compare_window_minutes": payload.get("defaultCompareWindowMinutes"),
                                "retention_days": payload.get("retentionDays"),
                                "target_url": payload.get("targetUrl"),
                                "session_cookie": payload.get("sessionCookie"),
                                "account_label_hint": payload.get("accountLabelHint"),
                                "request_timeout_seconds": payload.get("requestTimeoutSeconds"),
                            }
                        )
                        scheduler.wake()
                        self._write_json(HTTPStatus.OK, {"ok": True, "settings": settings.to_dict(camel=True)})
                        return
                    if parsed.path == "/api/capture/prepare":
                        preview = service.prepare_capture()
                        self._write_json(HTTPStatus.OK, {"ok": preview.ok, "preview": preview.to_dict(camel=True)})
                        return
                    if parsed.path == "/api/capture/start":
                        result = service.start_capture_session(payload.get("selectedVideoIds") or [])
                        scheduler.wake()
                        self._write_json(HTTPStatus.OK, {"ok": True, **result})
                        return
                    if parsed.path == "/api/capture/pause":
                        settings = service.set_capture_paused(bool(payload.get("paused")))
                        scheduler.wake()
                        self._write_json(HTTPStatus.OK, {"ok": True, "settings": settings.to_dict(camel=True)})
                        return
                    if parsed.path == "/api/capture/run":
                        result = service.run_capture()
                        self._write_json(HTTPStatus.OK, {"ok": True, "result": result.to_dict(camel=True)})
                        return
                except Exception as exc:  # noqa: BLE001
                    self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                    return
                self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})

            def log_message(self, format: str, *args: Any) -> None:
                return None

            def _serve_file(self, path: Path, content_type: str) -> None:
                try:
                    payload = path.read_bytes()
                except FileNotFoundError:
                    self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "File not found"})
                    return
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _read_json(self) -> dict[str, Any]:
                content_length = int(self.headers.get("Content-Length") or "0")
                if content_length <= 0:
                    return {}
                raw = self.rfile.read(content_length)
                return json.loads(raw.decode("utf-8")) if raw else {}

            def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
                raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        return Handler
