from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib import parse, request

from sph_flow.models import (
    CapturePreparationResult,
    CaptureRunResult,
    CapturedVideo,
    MonitorSettings,
    VideoMetrics,
    normalize_optional_video_title_text,
    normalize_video_title_text,
    parse_datetime_value,
)


@dataclass(slots=True)
class AccountIdentity:
    account_id: str | None = None
    account_label: str | None = None


class CollectorError(RuntimeError):
    pass


class WeixinChannelCollector:
    def prepare_capture(self, settings: MonitorSettings) -> CapturePreparationResult:
        account = self._read_account_identity(settings)
        videos = self._fetch_all_videos_from_post_list(settings)
        preview_videos = [self._to_captured_video(item, account) for item in videos]
        preview_videos = [video for video in preview_videos if video is not None]
        if not preview_videos:
            return CapturePreparationResult(
                ok=False,
                message="近期视频列表已读取，但没有找到可采集的视频。",
                account_id=account.account_id,
                account_label=account.account_label,
                videos=[],
            )
        return CapturePreparationResult(
            ok=True,
            message=f"成功读取 {len(preview_videos)} 条近期视频。",
            account_id=account.account_id,
            account_label=account.account_label,
            videos=preview_videos,
        )

    def capture(self, settings: MonitorSettings, selected_video_ids: list[str]) -> CaptureRunResult:
        account = self._read_account_identity(settings)
        videos = self._fetch_all_videos_from_post_list(settings)
        selected = {item.strip() for item in selected_video_ids if item and item.strip()}
        target_items = [item for item in videos if item.object_id and (not selected or item.object_id in selected)]
        if not target_items:
            return CaptureRunResult(
                ok=False,
                message="未匹配到这次要采集的视频，请重新刷新视频列表后再选择。",
                account_id=account.account_id,
                account_label=account.account_label,
                videos=[],
            )

        captured: list[CapturedVideo] = []
        for item in target_items:
            detail_metrics = self._fetch_detail_metrics(settings, item.object_id or "")
            captured.append(
                CapturedVideo(
                    video_id=item.object_id or "",
                    export_id=item.export_id,
                    object_id=item.object_id,
                    log_finder_id=item.log_finder_id,
                    account_id=account.account_id,
                    account_label=account.account_label,
                    title=item.title,
                    description=item.description,
                    publish_time=item.publish_time,
                    metrics=self._merge_metrics(self._create_overview_metrics(item), detail_metrics),
                )
            )

        return CaptureRunResult(
            ok=True,
            message=f"成功采集 {len(captured)} 条视频数据。",
            account_id=account.account_id,
            account_label=account.account_label,
            videos=captured,
        )

    def _request_json(self, settings: MonitorSettings, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if not settings.session_cookie.strip():
            raise CollectorError("请先在设置里填写视频号后台请求的 Cookie，再开始采集。")

        parsed = parse.urlparse(settings.target_url.rstrip("/"))
        endpoint = f"{parsed.scheme}://{parsed.netloc}{path}"
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "content-type": "application/json",
            "cookie": settings.session_cookie.strip(),
            "origin": f"{parsed.scheme}://{parsed.netloc}",
            "referer": settings.target_url,
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
            ),
        }
        req = request.Request(endpoint, data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=max(5, settings.request_timeout_seconds)) as response:
                raw = response.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            raise CollectorError(f"接口请求失败：{path}，{exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CollectorError(f"接口返回不是合法 JSON：{path}") from exc

        err_code = data.get("errCode")
        if isinstance(err_code, int) and err_code != 0:
            raise CollectorError(f"{path} 返回错误：{data.get('errMsg') or err_code}")
        return data

    def _read_account_identity(self, settings: MonitorSettings) -> AccountIdentity:
        label = settings.selected_account_label or settings.account_label_hint or None
        return AccountIdentity(
            account_id=settings.selected_account_id,
            account_label=label,
        )

    def _create_base_request_body(self, settings: MonitorSettings) -> dict[str, Any]:
        return {
            "timestamp": str(int(time.time() * 1000)),
            "_log_finder_uin": "",
            "_log_finder_id": settings.selected_account_id or "",
            "rawKeyBuff": None,
            "pluginSessionId": None,
            "scene": 7,
            "reqScene": 7,
        }

    def _get_statistic_range(self) -> tuple[int, int]:
        now = int(time.time())
        end_ts = ((now + 86399) // 86400) * 86400
        start_ts = end_ts - 30 * 24 * 60 * 60
        return start_ts, end_ts

    def _fetch_all_videos_from_post_list(self, settings: MonitorSettings) -> list["_PostListItem"]:
        start_ts, end_ts = self._get_statistic_range()
        page_size = 100
        current_page = 1
        total_count = 10**9
        items: list[_PostListItem] = []
        while len(items) < total_count:
            response = self._request_json(
                settings,
                "/micro/statistic/cgi-bin/mmfinderassistant-bin/statistic/post_list",
                {
                    **self._create_base_request_body(settings),
                    "pageSize": page_size,
                    "currentPage": current_page,
                    "sort": 0,
                    "order": 0,
                    "startTime": start_ts,
                    "endTime": end_ts,
                },
            )
            data = response.get("data") or {}
            raw_list = data.get("list") or []
            page_items = [self._map_post_list_item(item) for item in raw_list]
            items.extend(page_items)
            total_count = int(data.get("totalCount") or len(page_items))
            if len(page_items) < page_size:
                break
            current_page += 1
        if not items:
            raise CollectorError("post_list 没有返回任何视频数据，请检查 Cookie 是否有效。")
        return items

    def _fetch_detail_metrics(self, settings: MonitorSettings, feed_id: str) -> VideoMetrics:
        response = self._request_json(
            settings,
            "/micro/statistic/cgi-bin/mmfinderassistant-bin/statistic/feed_aggreagate_data_by_tab_type",
            {
                **self._create_base_request_body(settings),
                "startTs": str(int(time.time()) - 6 * 24 * 60 * 60),
                "endTs": str(int(time.time())),
                "interval": 3,
                "feedId": feed_id,
            },
        )
        feed_data = (((response.get("data") or {}).get("feedData") or [{}])[0].get("dataByTabtype")) or []
        totals = {
            "play_count": 0,
            "like_count": 0,
            "comment_count": 0,
            "share_count": 0,
            "follow_count": 0,
            "forward_chat_count": 0,
            "ringtone_count": 0,
            "status_count": 0,
            "cover_count": 0,
        }
        for item in feed_data:
            source = item.get("data") or {}
            totals["play_count"] += self._sum_metric_series(source.get("browse"))
            totals["like_count"] += self._sum_metric_series(source.get("like"))
            totals["comment_count"] += self._sum_metric_series(source.get("comment"))
            totals["share_count"] += self._sum_metric_series(source.get("forward"))
            totals["follow_count"] += self._sum_metric_series(source.get("follow"))
            totals["forward_chat_count"] += self._sum_metric_series(source.get("forwardAggregation"))
            totals["ringtone_count"] += self._sum_metric_series(source.get("ringset"))
            totals["status_count"] += self._sum_metric_series(source.get("statusref"))
            totals["cover_count"] += self._sum_metric_series(source.get("snscover"))
        return VideoMetrics(
            play_count=totals["play_count"],
            like_count=totals["like_count"],
            comment_count=totals["comment_count"],
            share_count=totals["share_count"],
            follow_count=totals["follow_count"],
            forward_chat_count=totals["forward_chat_count"],
            ringtone_count=totals["ringtone_count"],
            status_count=totals["status_count"],
            cover_count=totals["cover_count"],
        )

    def _sum_metric_series(self, values: Any) -> int:
        return sum(self._parse_integer(item) for item in (values or []))

    def _parse_integer(self, value: Any) -> int:
        digits = "".join(ch for ch in str(value or "") if ch.isdigit() or ch in {".", "-"})
        if not digits:
            return 0
        return int(float(digits))

    def _to_number(self, value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        return float(self._parse_integer(value))

    def _normalize_completion_rate(self, value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return numeric * 100 if numeric <= 1 else numeric

    def _to_datetime(self, value: Any) -> datetime | None:
        return parse_datetime_value(value)

    def _clean_text(self, value: Any) -> str:
        return " ".join(str(value or "").split()).strip()

    def _extract_text_field(self, value: Any) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for key in ("content", "value", "text", "title", "description"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate
        return None

    def _pick_video_description(self, item: dict[str, Any]) -> str | None:
        nested_description = None
        desc = item.get("desc")
        if isinstance(desc, dict):
            nested_description = self._extract_text_field(desc.get("description"))
        description = (
            nested_description
            or self._extract_text_field(item.get("description"))
            or self._extract_text_field(desc)
            or self._extract_text_field(item.get("feedDesc"))
            or self._extract_text_field(item.get("objectDesc"))
        )
        return normalize_optional_video_title_text(description)

    def _pick_log_finder_id(self, item: dict[str, Any]) -> str | None:
        value = item.get("logFinderId") or item.get("log_finder_id") or item.get("_log_finder_id")
        cleaned = self._clean_text(value)
        return cleaned or None

    def _pick_video_title(self, item: dict[str, Any]) -> str:
        description = self._pick_video_description(item)
        if description:
            return description
        title = normalize_video_title_text(
            self._extract_text_field(item.get("title")) or item.get("exportId") or item.get("objectId") or "未命名视频"
        )
        return title or "未命名视频"

    def _map_post_list_item(self, item: dict[str, Any]) -> "_PostListItem":
        return _PostListItem(
            title=self._pick_video_title(item),
            description=self._pick_video_description(item),
            publish_time=self._to_datetime(item.get("createTime")),
            export_id=item.get("exportId"),
            object_id=item.get("objectId"),
            log_finder_id=self._pick_log_finder_id(item),
            completion_rate=self._normalize_completion_rate(item.get("fullPlayRate")),
            avg_play_time_seconds=self._to_number(item.get("avgPlayTimeSec")),
            play_count=int(self._to_number(item.get("readCount"))),
            like_count=int(self._to_number(item.get("likeCount"))),
            comment_count=int(self._to_number(item.get("commentCount"))),
            share_count=int(self._to_number(item.get("forwardCount"))),
            follow_count=int(self._to_number(item.get("followCount"))),
            forward_chat_count=int(self._to_number(item.get("forwardAggregationCount"))),
            ringtone_count=int(self._to_number(item.get("ringsetCount"))),
            status_count=int(self._to_number(item.get("statusrefCount"))),
            cover_count=int(self._to_number(item.get("snscoverCount"))),
        )

    def _create_overview_metrics(self, item: "_PostListItem") -> VideoMetrics:
        return VideoMetrics(
            completion_rate=item.completion_rate,
            avg_play_time_seconds=item.avg_play_time_seconds,
            play_count=item.play_count,
            like_count=item.like_count,
            comment_count=item.comment_count,
            share_count=item.share_count,
            follow_count=item.follow_count,
            forward_chat_count=item.forward_chat_count,
            ringtone_count=item.ringtone_count,
            status_count=item.status_count,
            cover_count=item.cover_count,
        )

    def _merge_metrics(self, overview: VideoMetrics, detail: VideoMetrics) -> VideoMetrics:
        return VideoMetrics(
            completion_rate=overview.completion_rate,
            avg_play_time_seconds=overview.avg_play_time_seconds,
            play_count=detail.play_count or overview.play_count,
            like_count=detail.like_count or overview.like_count,
            comment_count=detail.comment_count or overview.comment_count,
            share_count=detail.share_count or overview.share_count,
            follow_count=detail.follow_count or overview.follow_count,
            forward_chat_count=detail.forward_chat_count or overview.forward_chat_count,
            ringtone_count=detail.ringtone_count or overview.ringtone_count,
            status_count=detail.status_count or overview.status_count,
            cover_count=detail.cover_count or overview.cover_count,
        )

    def _to_captured_video(self, item: "_PostListItem", account: AccountIdentity) -> CapturedVideo | None:
        if not item.object_id:
            return None
        account_id = account.account_id or item.log_finder_id
        account_label = account.account_label or account_id
        return CapturedVideo(
            video_id=item.object_id,
            export_id=item.export_id,
            object_id=item.object_id,
            log_finder_id=item.log_finder_id,
            account_id=account_id,
            account_label=account_label,
            title=item.title,
            description=item.description,
            publish_time=item.publish_time,
            metrics=self._create_overview_metrics(item),
        )


@dataclass(slots=True)
class _PostListItem:
    title: str
    description: str | None
    publish_time: datetime | None
    export_id: str | None
    object_id: str | None
    log_finder_id: str | None
    completion_rate: float
    avg_play_time_seconds: float
    play_count: int
    like_count: int
    comment_count: int
    share_count: int
    follow_count: int
    forward_chat_count: int
    ringtone_count: int
    status_count: int
    cover_count: int
