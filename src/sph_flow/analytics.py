from __future__ import annotations

from datetime import datetime
from typing import Any

from sph_flow.models import MetricsDelta, VideoMetrics, normalize_datetime_to_minute, to_epoch_millis


def normalize_timestamp_to_minute(timestamp: Any) -> datetime:
    return normalize_datetime_to_minute(timestamp)


def create_snapshot_id(video_id: str, captured_at: Any) -> str:
    return f"{video_id}_{to_epoch_millis(captured_at)}"


def diff_metrics(start: VideoMetrics | None, end: VideoMetrics | None) -> MetricsDelta:
    if end is None:
        return MetricsDelta()

    left = start or VideoMetrics()
    return MetricsDelta(
        completion_rate=end.completion_rate - left.completion_rate,
        avg_play_time_seconds=end.avg_play_time_seconds - left.avg_play_time_seconds,
        play_count=end.play_count - left.play_count,
        like_count=end.like_count - left.like_count,
        comment_count=end.comment_count - left.comment_count,
        share_count=end.share_count - left.share_count,
        follow_count=end.follow_count - left.follow_count,
        forward_chat_count=end.forward_chat_count - left.forward_chat_count,
        ringtone_count=end.ringtone_count - left.ringtone_count,
        status_count=end.status_count - left.status_count,
        cover_count=end.cover_count - left.cover_count,
    )
