from __future__ import annotations

import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from sph_flow.collector import CollectorError, WeixinChannelCollector
from sph_flow.models import CapturePreparationResult, CaptureRunResult, MonitorSettings, format_datetime_text, now_display_time
from sph_flow.storage import Storage
from sph_flow.xlsx_export import build_snapshots_workbook


class MonitorService:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.storage = Storage(root_dir / "data" / "monitor_store.db")
        self.collector = WeixinChannelCollector()
        self._capture_lock = threading.Lock()

    def get_settings(self) -> MonitorSettings:
        return self.storage.get_settings()

    def save_settings(self, partial_settings: dict[str, Any]) -> MonitorSettings:
        return self.storage.save_settings(partial_settings)

    def get_status_bundle(self) -> dict[str, Any]:
        settings = self.get_settings()
        status = self.storage.get_status()
        recent = self.storage.list_recent_snapshots(10)
        return {
            "status": status.to_dict(camel=True),
            "settings": settings.to_dict(camel=True),
            "recentSnapshots": [item.to_dict(camel=True) for item in recent],
            "hasCaptureHistory": bool(recent),
        }

    def prepare_capture(self) -> CapturePreparationResult:
        settings = self.get_settings()
        try:
            return self.collector.prepare_capture(settings)
        except CollectorError as exc:
            return CapturePreparationResult(ok=False, message=str(exc), videos=[])

    def start_capture_session(self, selected_video_ids: list[str]) -> dict[str, Any]:
        normalized = _normalize_selected_video_ids(selected_video_ids)
        if not normalized:
            raise ValueError("请至少选择一个要采集的视频。")

        preview = self.prepare_capture()
        if not preview.ok:
            raise RuntimeError(preview.message)

        settings = self.save_settings(
            {
                "capture_paused": False,
                "selected_video_ids": normalized,
                "selected_account_id": preview.account_id,
                "selected_account_label": preview.account_label,
            }
        )
        result = self.run_capture()
        return {
            "settings": settings.to_dict(camel=True),
            "result": result.to_dict(camel=True),
        }

    def run_capture(self) -> CaptureRunResult:
        if not self._capture_lock.acquire(blocking=False):
            raise RuntimeError("后台采集正在进行中，请稍后再试。")

        started_at = now_display_time()
        settings = self.get_settings()
        selected_video_ids = _normalize_selected_video_ids(settings.selected_video_ids)
        self.storage.save_status(
            {
                "last_run_at": started_at,
                "last_error": None,
                "last_message": "正在采集已选视频..." if selected_video_ids else "正在采集...",
                "account_label": settings.selected_account_label or settings.account_label_hint or None,
            }
        )

        try:
            result = self.collector.capture(settings, selected_video_ids)
            if not result.ok:
                raise RuntimeError(result.message)

            account_label = result.account_label or settings.selected_account_label or settings.account_label_hint or None
            account_id = result.account_id or settings.selected_account_id or None
            for video in result.videos:
                self.storage.save_snapshot(
                    video_id=video.video_id,
                    export_id=video.export_id,
                    object_id=video.object_id,
                    log_finder_id=video.log_finder_id,
                    account_id=video.account_id or account_id,
                    account_label=video.account_label or account_label,
                    video_title=video.title,
                    description=video.description,
                    publish_time=video.publish_time,
                    metrics=video.metrics,
                    source_page=settings.target_url,
                )

            self.storage.prune_expired_snapshots(settings.retention_days)
            self.storage.save_status(
                {
                    "last_success_at": now_display_time(),
                    "last_error": None,
                    "last_message": result.message,
                    "account_label": account_label,
                }
            )
            return result
        except Exception as exc:  # noqa: BLE001
            self.storage.save_status(
                {
                    "last_error": str(exc),
                    "last_message": None,
                    "account_label": settings.selected_account_label or settings.account_label_hint or None,
                }
            )
            raise
        finally:
            self._capture_lock.release()

    def set_capture_paused(self, paused: bool) -> MonitorSettings:
        return self.save_settings({"capture_paused": bool(paused)})

    def list_window_stats(self, window_minutes: int) -> dict[str, Any]:
        rows = self.storage.list_window_stats(window_minutes)
        return {"rows": [row.to_dict(camel=True) for row in rows]}

    def build_trend_points(self, video_id: str, metric: str, window_minutes: int = 1) -> dict[str, Any]:
        snapshots = self.storage.get_snapshots_for_video(video_id)
        if not snapshots:
            return {"points": []}
        period = timedelta(minutes=max(1, int(window_minutes or 1)))
        metric_attr = _metric_name_to_attr(metric)
        points = []
        previous_value: int | float | None = None
        previous_captured_at = None
        for snapshot in snapshots:
            if snapshot.captured_at is None:
                continue
            if previous_captured_at is not None and snapshot.captured_at < previous_captured_at + period:
                continue
            value = getattr(snapshot.metrics, metric_attr, 0)
            growth = 0 if previous_value is None else value - previous_value
            points.append(
                {
                    "capturedAt": format_datetime_text(snapshot.captured_at),
                    "value": value,
                    "growth": growth,
                }
            )
            previous_value = value
            previous_captured_at = snapshot.captured_at
        return {"points": points}

    def export_snapshots_xlsx(self) -> bytes:
        return build_snapshots_workbook(self.storage.list_all_snapshots())


class CaptureScheduler:
    def __init__(self, service: MonitorService) -> None:
        self.service = service
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="capture-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def wake(self) -> None:
        self._wake_event.set()

    def _run(self) -> None:
        next_run_at = _now_ms()
        while not self._stop_event.is_set():
            settings = self.service.get_settings()
            if settings.capture_paused or not settings.selected_video_ids:
                self._wake_event.wait(timeout=1)
                self._wake_event.clear()
                next_run_at = _now_ms() + settings.poll_interval_minutes * 60_000
                continue

            now = _now_ms()
            if now < next_run_at:
                self._wake_event.wait(timeout=min(1.0, max(0.1, (next_run_at - now) / 1000)))
                self._wake_event.clear()
                continue

            try:
                self.service.run_capture()
            except Exception:  # noqa: BLE001
                pass
            settings = self.service.get_settings()
            next_run_at = _now_ms() + settings.poll_interval_minutes * 60_000


def _normalize_selected_video_ids(selected_video_ids: list[str] | None) -> list[str]:
    return list(dict.fromkeys(str(item).strip() for item in selected_video_ids or [] if str(item).strip()))


def _metric_name_to_attr(metric: str) -> str:
    mapping = {
        "completionRate": "completion_rate",
        "avgPlayTimeSeconds": "avg_play_time_seconds",
        "playCount": "play_count",
        "likeCount": "like_count",
        "commentCount": "comment_count",
        "shareCount": "share_count",
        "followCount": "follow_count",
        "forwardChatCount": "forward_chat_count",
        "ringtoneCount": "ringtone_count",
        "statusCount": "status_count",
        "coverCount": "cover_count",
    }
    return mapping.get(metric, "play_count")


def _now_ms() -> int:
    return int(time.time() * 1000)
