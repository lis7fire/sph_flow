from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from sph_flow.analytics import create_snapshot_id, diff_metrics, normalize_timestamp_to_minute
from sph_flow.models import CaptureStatus, MetricsDelta, MonitorSettings, VideoMetrics, VideoRecord, VideoSnapshot, VideoWindowStats


class Storage:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=MEMORY;")
        connection.execute("PRAGMA temp_store=MEMORY;")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS status (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS videos (
                    video_id TEXT PRIMARY KEY,
                    export_id TEXT,
                    object_id TEXT,
                    log_finder_id TEXT,
                    account_id TEXT,
                    account_label TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    publish_time INTEGER,
                    last_captured_at INTEGER NOT NULL,
                    completion_rate REAL NOT NULL,
                    avg_play_time_seconds REAL NOT NULL,
                    play_count INTEGER NOT NULL,
                    like_count INTEGER NOT NULL,
                    comment_count INTEGER NOT NULL,
                    share_count INTEGER NOT NULL,
                    follow_count INTEGER NOT NULL,
                    forward_chat_count INTEGER NOT NULL,
                    ringtone_count INTEGER NOT NULL,
                    status_count INTEGER NOT NULL,
                    cover_count INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL,
                    export_id TEXT,
                    object_id TEXT,
                    log_finder_id TEXT,
                    account_id TEXT,
                    account_label TEXT,
                    video_title TEXT NOT NULL,
                    description TEXT,
                    publish_time INTEGER,
                    captured_at INTEGER NOT NULL,
                    source_page TEXT,
                    completion_rate REAL NOT NULL,
                    avg_play_time_seconds REAL NOT NULL,
                    play_count INTEGER NOT NULL,
                    like_count INTEGER NOT NULL,
                    comment_count INTEGER NOT NULL,
                    share_count INTEGER NOT NULL,
                    follow_count INTEGER NOT NULL,
                    forward_chat_count INTEGER NOT NULL,
                    ringtone_count INTEGER NOT NULL,
                    status_count INTEGER NOT NULL,
                    cover_count INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_snapshots_captured_at ON snapshots(captured_at);
                CREATE INDEX IF NOT EXISTS idx_snapshots_video_id ON snapshots(video_id);
                CREATE INDEX IF NOT EXISTS idx_snapshots_video_captured ON snapshots(video_id, captured_at);
                """
            )

    def get_settings(self) -> MonitorSettings:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key = ?", ("monitor-settings",)).fetchone()
        payload = json.loads(row["value"]) if row else {}
        return MonitorSettings.from_dict(payload)

    def save_settings(self, partial_settings: dict[str, Any]) -> MonitorSettings:
        current = self.get_settings()
        merged = current.to_dict()
        merged.update(partial_settings)
        settings = MonitorSettings.from_dict(merged)
        with self._lock, self._connect() as connection:
            connection.execute(
                "REPLACE INTO settings(key, value) VALUES(?, ?)",
                ("monitor-settings", json.dumps(settings.to_dict(), ensure_ascii=False)),
            )
        return settings

    def get_status(self) -> CaptureStatus:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT value FROM status WHERE key = ?", ("capture-status",)).fetchone()
        payload = json.loads(row["value"]) if row else {}
        return CaptureStatus.from_dict(payload)

    def save_status(self, partial_status: dict[str, Any]) -> CaptureStatus:
        current = self.get_status()
        merged = current.to_dict()
        merged.update(partial_status)
        status = CaptureStatus.from_dict(merged)
        with self._lock, self._connect() as connection:
            connection.execute(
                "REPLACE INTO status(key, value) VALUES(?, ?)",
                ("capture-status", json.dumps(status.to_dict(), ensure_ascii=False)),
            )
        return status

    def save_snapshot(
        self,
        *,
        video_id: str,
        export_id: str | None,
        object_id: str | None,
        log_finder_id: str | None,
        account_id: str | None,
        account_label: str | None,
        video_title: str,
        description: str | None,
        publish_time: int | None,
        metrics: VideoMetrics,
        source_page: str | None,
        captured_at: int | None = None,
    ) -> VideoSnapshot:
        normalized_captured_at = normalize_timestamp_to_minute(captured_at or _now_ms())
        snapshot = VideoSnapshot(
            id=create_snapshot_id(video_id, normalized_captured_at),
            video_id=video_id,
            export_id=export_id,
            object_id=object_id,
            log_finder_id=log_finder_id,
            account_id=account_id,
            account_label=account_label,
            video_title=video_title,
            description=description,
            publish_time=publish_time,
            captured_at=normalized_captured_at,
            metrics=metrics,
            source_page=source_page,
        )

        with self._lock, self._connect() as connection:
            connection.execute(
                """
                REPLACE INTO snapshots(
                    id, video_id, export_id, object_id, log_finder_id, account_id, account_label,
                    video_title, description, publish_time, captured_at, source_page,
                    completion_rate, avg_play_time_seconds, play_count, like_count, comment_count, share_count,
                    follow_count, forward_chat_count, ringtone_count, status_count, cover_count
                ) VALUES(
                    :id, :video_id, :export_id, :object_id, :log_finder_id, :account_id, :account_label,
                    :video_title, :description, :publish_time, :captured_at, :source_page,
                    :completion_rate, :avg_play_time_seconds, :play_count, :like_count, :comment_count, :share_count,
                    :follow_count, :forward_chat_count, :ringtone_count, :status_count, :cover_count
                )
                """,
                _snapshot_db_params(snapshot),
            )
            connection.execute(
                """
                REPLACE INTO videos(
                    video_id, export_id, object_id, log_finder_id, account_id, account_label,
                    title, description, publish_time, last_captured_at,
                    completion_rate, avg_play_time_seconds, play_count, like_count, comment_count, share_count,
                    follow_count, forward_chat_count, ringtone_count, status_count, cover_count
                ) VALUES(
                    :video_id, :export_id, :object_id, :log_finder_id, :account_id, :account_label,
                    :title, :description, :publish_time, :last_captured_at,
                    :completion_rate, :avg_play_time_seconds, :play_count, :like_count, :comment_count, :share_count,
                    :follow_count, :forward_chat_count, :ringtone_count, :status_count, :cover_count
                )
                """,
                _video_db_params(
                    VideoRecord(
                        video_id=video_id,
                        export_id=export_id,
                        object_id=object_id,
                        log_finder_id=log_finder_id,
                        account_id=account_id,
                        account_label=account_label,
                        title=video_title,
                        description=description,
                        publish_time=publish_time,
                        last_captured_at=normalized_captured_at,
                        last_metrics=metrics,
                    )
                ),
            )
        return snapshot

    def list_recent_snapshots(self, limit: int = 10) -> list[VideoSnapshot]:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT * FROM snapshots ORDER BY captured_at DESC LIMIT ?", (max(1, limit),)).fetchall()
        return [_snapshot_from_row(row) for row in rows]

    def list_all_snapshots(self) -> list[VideoSnapshot]:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT * FROM snapshots ORDER BY captured_at DESC").fetchall()
        return [_snapshot_from_row(row) for row in rows]

    def list_videos(self) -> list[VideoRecord]:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT * FROM videos ORDER BY last_captured_at DESC").fetchall()
        return [_video_from_row(row) for row in rows]

    def get_snapshots_for_video(self, video_id: str) -> list[VideoSnapshot]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM snapshots WHERE video_id = ? ORDER BY captured_at ASC",
                (video_id,),
            ).fetchall()
        return [_snapshot_from_row(row) for row in rows]

    def get_latest_snapshot_before(self, video_id: str, timestamp: int) -> VideoSnapshot | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM snapshots
                WHERE video_id = ? AND captured_at <= ?
                ORDER BY captured_at DESC
                LIMIT 1
                """,
                (video_id, timestamp),
            ).fetchone()
        return _snapshot_from_row(row) if row else None

    def list_window_stats(self, window_minutes: int, end_time: int | None = None) -> list[VideoWindowStats]:
        normalized_end = normalize_timestamp_to_minute(end_time or _now_ms())
        window_start = normalized_end - max(1, window_minutes) * 60_000
        rows: list[VideoWindowStats] = []
        for video in self.list_videos():
            start_snapshot = self.get_latest_snapshot_before(video.video_id, window_start)
            end_snapshot = self.get_latest_snapshot_before(video.video_id, normalized_end)
            has_enough_data = bool(start_snapshot and end_snapshot)
            rows.append(
                VideoWindowStats(
                    video_id=video.video_id,
                    title=video.title,
                    description=video.description,
                    publish_time=video.publish_time,
                    last_captured_at=video.last_captured_at,
                    window_start=window_start,
                    window_end=normalized_end,
                    start_snapshot=start_snapshot,
                    end_snapshot=end_snapshot,
                    delta=diff_metrics(
                        start_snapshot.metrics if start_snapshot else None,
                        end_snapshot.metrics if end_snapshot else None,
                    )
                    if has_enough_data
                    else MetricsDelta(),
                    has_enough_data=has_enough_data,
                )
            )
        rows.sort(key=lambda item: (not item.has_enough_data, -item.delta.play_count, -item.last_captured_at))
        return rows

    def prune_expired_snapshots(self, retention_days: int) -> None:
        cutoff = _now_ms() - max(1, retention_days) * 24 * 60 * 60 * 1000
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM snapshots WHERE captured_at <= ?", (cutoff,))


def _snapshot_db_params(snapshot: VideoSnapshot) -> dict[str, Any]:
    metrics = snapshot.metrics
    return {
        "id": snapshot.id,
        "video_id": snapshot.video_id,
        "export_id": snapshot.export_id,
        "object_id": snapshot.object_id,
        "log_finder_id": snapshot.log_finder_id,
        "account_id": snapshot.account_id,
        "account_label": snapshot.account_label,
        "video_title": snapshot.video_title,
        "description": snapshot.description,
        "publish_time": snapshot.publish_time,
        "captured_at": snapshot.captured_at,
        "source_page": snapshot.source_page,
        "completion_rate": metrics.completion_rate,
        "avg_play_time_seconds": metrics.avg_play_time_seconds,
        "play_count": metrics.play_count,
        "like_count": metrics.like_count,
        "comment_count": metrics.comment_count,
        "share_count": metrics.share_count,
        "follow_count": metrics.follow_count,
        "forward_chat_count": metrics.forward_chat_count,
        "ringtone_count": metrics.ringtone_count,
        "status_count": metrics.status_count,
        "cover_count": metrics.cover_count,
    }


def _video_db_params(video: VideoRecord) -> dict[str, Any]:
    metrics = video.last_metrics
    return {
        "video_id": video.video_id,
        "export_id": video.export_id,
        "object_id": video.object_id,
        "log_finder_id": video.log_finder_id,
        "account_id": video.account_id,
        "account_label": video.account_label,
        "title": video.title,
        "description": video.description,
        "publish_time": video.publish_time,
        "last_captured_at": video.last_captured_at,
        "completion_rate": metrics.completion_rate,
        "avg_play_time_seconds": metrics.avg_play_time_seconds,
        "play_count": metrics.play_count,
        "like_count": metrics.like_count,
        "comment_count": metrics.comment_count,
        "share_count": metrics.share_count,
        "follow_count": metrics.follow_count,
        "forward_chat_count": metrics.forward_chat_count,
        "ringtone_count": metrics.ringtone_count,
        "status_count": metrics.status_count,
        "cover_count": metrics.cover_count,
    }


def _metrics_from_row(row: sqlite3.Row) -> VideoMetrics:
    return VideoMetrics(
        completion_rate=float(row["completion_rate"] or 0),
        avg_play_time_seconds=float(row["avg_play_time_seconds"] or 0),
        play_count=int(row["play_count"] or 0),
        like_count=int(row["like_count"] or 0),
        comment_count=int(row["comment_count"] or 0),
        share_count=int(row["share_count"] or 0),
        follow_count=int(row["follow_count"] or 0),
        forward_chat_count=int(row["forward_chat_count"] or 0),
        ringtone_count=int(row["ringtone_count"] or 0),
        status_count=int(row["status_count"] or 0),
        cover_count=int(row["cover_count"] or 0),
    )


def _snapshot_from_row(row: sqlite3.Row) -> VideoSnapshot:
    return VideoSnapshot(
        id=row["id"],
        video_id=row["video_id"],
        export_id=row["export_id"],
        object_id=row["object_id"],
        log_finder_id=row["log_finder_id"],
        account_id=row["account_id"],
        account_label=row["account_label"],
        video_title=row["video_title"],
        description=row["description"],
        publish_time=row["publish_time"],
        captured_at=row["captured_at"],
        metrics=_metrics_from_row(row),
        source_page=row["source_page"],
    )


def _video_from_row(row: sqlite3.Row) -> VideoRecord:
    return VideoRecord(
        video_id=row["video_id"],
        export_id=row["export_id"],
        object_id=row["object_id"],
        log_finder_id=row["log_finder_id"],
        account_id=row["account_id"],
        account_label=row["account_label"],
        title=row["title"],
        description=row["description"],
        publish_time=row["publish_time"],
        last_captured_at=row["last_captured_at"],
        last_metrics=_metrics_from_row(row),
    )


def _now_ms() -> int:
    return int(time.time() * 1000)
