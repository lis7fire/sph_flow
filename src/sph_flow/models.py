from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class VideoMetrics:
    completion_rate: float = 0.0
    avg_play_time_seconds: float = 0.0
    play_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    follow_count: int = 0
    forward_chat_count: int = 0
    ringtone_count: int = 0
    status_count: int = 0
    cover_count: int = 0

    def to_dict(self, *, camel: bool = False) -> dict[str, float | int]:
        payload = asdict(self)
        if not camel:
            return payload
        return {
            "completionRate": payload["completion_rate"],
            "avgPlayTimeSeconds": payload["avg_play_time_seconds"],
            "playCount": payload["play_count"],
            "likeCount": payload["like_count"],
            "commentCount": payload["comment_count"],
            "shareCount": payload["share_count"],
            "followCount": payload["follow_count"],
            "forwardChatCount": payload["forward_chat_count"],
            "ringtoneCount": payload["ringtone_count"],
            "statusCount": payload["status_count"],
            "coverCount": payload["cover_count"],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "VideoMetrics":
        data = payload or {}
        return cls(
            completion_rate=float(data.get("completion_rate", data.get("completionRate", 0)) or 0),
            avg_play_time_seconds=float(data.get("avg_play_time_seconds", data.get("avgPlayTimeSeconds", 0)) or 0),
            play_count=int(data.get("play_count", data.get("playCount", 0)) or 0),
            like_count=int(data.get("like_count", data.get("likeCount", 0)) or 0),
            comment_count=int(data.get("comment_count", data.get("commentCount", 0)) or 0),
            share_count=int(data.get("share_count", data.get("shareCount", 0)) or 0),
            follow_count=int(data.get("follow_count", data.get("followCount", 0)) or 0),
            forward_chat_count=int(data.get("forward_chat_count", data.get("forwardChatCount", 0)) or 0),
            ringtone_count=int(data.get("ringtone_count", data.get("ringtoneCount", 0)) or 0),
            status_count=int(data.get("status_count", data.get("statusCount", 0)) or 0),
            cover_count=int(data.get("cover_count", data.get("coverCount", 0)) or 0),
        )


@dataclass(slots=True)
class MetricsDelta(VideoMetrics):
    pass


@dataclass(slots=True)
class VideoSnapshot:
    id: str
    video_id: str
    export_id: str | None = None
    object_id: str | None = None
    log_finder_id: str | None = None
    account_id: str | None = None
    account_label: str | None = None
    video_title: str = ""
    description: str | None = None
    publish_time: int | None = None
    captured_at: int = 0
    metrics: VideoMetrics = field(default_factory=VideoMetrics)
    source_page: str | None = None

    def to_dict(self, *, camel: bool = False) -> dict[str, Any]:
        if not camel:
            return {
                "id": self.id,
                "video_id": self.video_id,
                "export_id": self.export_id,
                "object_id": self.object_id,
                "log_finder_id": self.log_finder_id,
                "account_id": self.account_id,
                "account_label": self.account_label,
                "video_title": self.video_title,
                "description": self.description,
                "publish_time": self.publish_time,
                "captured_at": self.captured_at,
                "metrics": self.metrics.to_dict(),
                "source_page": self.source_page,
            }
        return {
            "id": self.id,
            "videoId": self.video_id,
            "exportId": self.export_id,
            "objectId": self.object_id,
            "logFinderId": self.log_finder_id,
            "accountId": self.account_id,
            "accountLabel": self.account_label,
            "videoTitle": self.video_title,
            "description": self.description,
            "publishTime": self.publish_time,
            "capturedAt": self.captured_at,
            "metrics": self.metrics.to_dict(camel=True),
            "sourcePage": self.source_page,
        }


@dataclass(slots=True)
class VideoRecord:
    video_id: str
    export_id: str | None = None
    object_id: str | None = None
    log_finder_id: str | None = None
    account_id: str | None = None
    account_label: str | None = None
    title: str = ""
    description: str | None = None
    publish_time: int | None = None
    last_captured_at: int = 0
    last_metrics: VideoMetrics = field(default_factory=VideoMetrics)

    def to_dict(self, *, camel: bool = False) -> dict[str, Any]:
        if not camel:
            return {
                "video_id": self.video_id,
                "export_id": self.export_id,
                "object_id": self.object_id,
                "log_finder_id": self.log_finder_id,
                "account_id": self.account_id,
                "account_label": self.account_label,
                "title": self.title,
                "description": self.description,
                "publish_time": self.publish_time,
                "last_captured_at": self.last_captured_at,
                "last_metrics": self.last_metrics.to_dict(),
            }
        return {
            "videoId": self.video_id,
            "exportId": self.export_id,
            "objectId": self.object_id,
            "logFinderId": self.log_finder_id,
            "accountId": self.account_id,
            "accountLabel": self.account_label,
            "title": self.title,
            "description": self.description,
            "publishTime": self.publish_time,
            "lastCapturedAt": self.last_captured_at,
            "lastMetrics": self.last_metrics.to_dict(camel=True),
        }


@dataclass(slots=True)
class MonitorSettings:
    poll_interval_minutes: int = 1
    default_compare_window_minutes: int = 5
    retention_days: int = 30
    target_url: str = "https://channels.weixin.qq.com/platform/statistic/post"
    capture_paused: bool = False
    selected_video_ids: list[str] = field(default_factory=list)
    selected_account_id: str | None = None
    selected_account_label: str | None = None
    session_cookie: str = ""
    account_label_hint: str = ""
    request_timeout_seconds: int = 20
    listen_host: str = "127.0.0.1"
    listen_port: int = 8765

    def to_dict(self, *, camel: bool = False) -> dict[str, Any]:
        payload = asdict(self)
        if not camel:
            return payload
        return {
            "pollIntervalMinutes": payload["poll_interval_minutes"],
            "defaultCompareWindowMinutes": payload["default_compare_window_minutes"],
            "retentionDays": payload["retention_days"],
            "targetUrl": payload["target_url"],
            "capturePaused": payload["capture_paused"],
            "selectedVideoIds": payload["selected_video_ids"],
            "selectedAccountId": payload["selected_account_id"],
            "selectedAccountLabel": payload["selected_account_label"],
            "sessionCookie": payload["session_cookie"],
            "accountLabelHint": payload["account_label_hint"],
            "requestTimeoutSeconds": payload["request_timeout_seconds"],
            "listenHost": payload["listen_host"],
            "listenPort": payload["listen_port"],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "MonitorSettings":
        data = payload or {}
        return cls(
            poll_interval_minutes=max(1, int(data.get("poll_interval_minutes", data.get("pollIntervalMinutes", 1)) or 1)),
            default_compare_window_minutes=max(
                1,
                int(data.get("default_compare_window_minutes", data.get("defaultCompareWindowMinutes", 5)) or 5),
            ),
            retention_days=max(1, int(data.get("retention_days", data.get("retentionDays", 30)) or 30)),
            target_url=str(data.get("target_url", data.get("targetUrl", cls().target_url)) or cls().target_url),
            capture_paused=bool(data.get("capture_paused", data.get("capturePaused", False))),
            selected_video_ids=[
                str(item).strip()
                for item in data.get("selected_video_ids", data.get("selectedVideoIds", [])) or []
                if str(item).strip()
            ],
            selected_account_id=_normalize_optional_text(data.get("selected_account_id", data.get("selectedAccountId"))),
            selected_account_label=_normalize_optional_text(
                data.get("selected_account_label", data.get("selectedAccountLabel"))
            ),
            session_cookie=str(data.get("session_cookie", data.get("sessionCookie", "")) or ""),
            account_label_hint=str(data.get("account_label_hint", data.get("accountLabelHint", "")) or ""),
            request_timeout_seconds=max(
                5,
                int(data.get("request_timeout_seconds", data.get("requestTimeoutSeconds", 20)) or 20),
            ),
            listen_host=str(data.get("listen_host", data.get("listenHost", "127.0.0.1")) or "127.0.0.1"),
            listen_port=max(1, int(data.get("listen_port", data.get("listenPort", 8765)) or 8765)),
        )


@dataclass(slots=True)
class CaptureStatus:
    last_run_at: int | None = None
    last_success_at: int | None = None
    last_error: str | None = None
    last_message: str | None = None
    account_label: str | None = None

    def to_dict(self, *, camel: bool = False) -> dict[str, Any]:
        payload = asdict(self)
        if not camel:
            return payload
        return {
            "lastRunAt": payload["last_run_at"],
            "lastSuccessAt": payload["last_success_at"],
            "lastError": payload["last_error"],
            "lastMessage": payload["last_message"],
            "accountLabel": payload["account_label"],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "CaptureStatus":
        data = payload or {}
        return cls(
            last_run_at=data.get("last_run_at", data.get("lastRunAt")),
            last_success_at=data.get("last_success_at", data.get("lastSuccessAt")),
            last_error=_normalize_optional_text(data.get("last_error", data.get("lastError"))),
            last_message=_normalize_optional_text(data.get("last_message", data.get("lastMessage"))),
            account_label=_normalize_optional_text(data.get("account_label", data.get("accountLabel"))),
        )


@dataclass(slots=True)
class WindowStats:
    video_id: str
    start_snapshot: VideoSnapshot | None
    end_snapshot: VideoSnapshot | None
    delta: MetricsDelta

    def to_dict(self, *, camel: bool = False) -> dict[str, Any]:
        if not camel:
            return {
                "video_id": self.video_id,
                "start_snapshot": self.start_snapshot.to_dict() if self.start_snapshot else None,
                "end_snapshot": self.end_snapshot.to_dict() if self.end_snapshot else None,
                "delta": self.delta.to_dict(),
            }
        return {
            "videoId": self.video_id,
            "startSnapshot": self.start_snapshot.to_dict(camel=True) if self.start_snapshot else None,
            "endSnapshot": self.end_snapshot.to_dict(camel=True) if self.end_snapshot else None,
            "delta": self.delta.to_dict(camel=True),
        }


@dataclass(slots=True)
class VideoWindowStats(WindowStats):
    title: str = ""
    description: str | None = None
    publish_time: int | None = None
    last_captured_at: int = 0
    window_start: int = 0
    window_end: int = 0
    has_enough_data: bool = False

    def to_dict(self, *, camel: bool = False) -> dict[str, Any]:
        payload = super().to_dict(camel=camel)
        if not camel:
            payload.update(
                {
                    "title": self.title,
                    "description": self.description,
                    "publish_time": self.publish_time,
                    "last_captured_at": self.last_captured_at,
                    "window_start": self.window_start,
                    "window_end": self.window_end,
                    "has_enough_data": self.has_enough_data,
                }
            )
            return payload
        payload.update(
            {
                "title": self.title,
                "description": self.description,
                "publishTime": self.publish_time,
                "lastCapturedAt": self.last_captured_at,
                "windowStart": self.window_start,
                "windowEnd": self.window_end,
                "hasEnoughData": self.has_enough_data,
            }
        )
        return payload


@dataclass(slots=True)
class CapturedVideo:
    video_id: str
    export_id: str | None = None
    object_id: str | None = None
    log_finder_id: str | None = None
    account_id: str | None = None
    account_label: str | None = None
    title: str = ""
    description: str | None = None
    publish_time: int | None = None
    metrics: VideoMetrics = field(default_factory=VideoMetrics)

    def to_dict(self, *, camel: bool = False) -> dict[str, Any]:
        if not camel:
            return {
                "video_id": self.video_id,
                "export_id": self.export_id,
                "object_id": self.object_id,
                "log_finder_id": self.log_finder_id,
                "account_id": self.account_id,
                "account_label": self.account_label,
                "title": self.title,
                "description": self.description,
                "publish_time": self.publish_time,
                "metrics": self.metrics.to_dict(),
            }
        return {
            "videoId": self.video_id,
            "exportId": self.export_id,
            "objectId": self.object_id,
            "logFinderId": self.log_finder_id,
            "accountId": self.account_id,
            "accountLabel": self.account_label,
            "title": self.title,
            "description": self.description,
            "publishTime": self.publish_time,
            "metrics": self.metrics.to_dict(camel=True),
        }


@dataclass(slots=True)
class CapturePreparationResult:
    ok: bool
    message: str
    account_id: str | None = None
    account_label: str | None = None
    videos: list[CapturedVideo] = field(default_factory=list)

    def to_dict(self, *, camel: bool = False) -> dict[str, Any]:
        if not camel:
            return {
                "ok": self.ok,
                "message": self.message,
                "account_id": self.account_id,
                "account_label": self.account_label,
                "videos": [video.to_dict() for video in self.videos],
            }
        return {
            "ok": self.ok,
            "message": self.message,
            "accountId": self.account_id,
            "accountLabel": self.account_label,
            "videos": [video.to_dict(camel=True) for video in self.videos],
        }


@dataclass(slots=True)
class CaptureRunResult(CapturePreparationResult):
    pass


def _normalize_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
