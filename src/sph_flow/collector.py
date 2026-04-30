from __future__ import annotations

import hashlib
import json
import logging
import socket
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib import error as urlerror, parse, request

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

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AccountIdentity:
    account_id: str | None = None
    account_label: str | None = None


class CollectorError(RuntimeError):
    pass


class WeixinChannelCollector:
    def fetch_account_identity(self, settings: MonitorSettings) -> AccountIdentity:
        query = {
            "_aid": str(uuid.uuid4()),
            "_rid": uuid.uuid4().hex[:8],
            "_pageUrl": _platform_url(settings),
        }
        response = self._request_json(
            settings,
            f"/cgi-bin/mmfinderassistant-bin/auth/auth_data?{parse.urlencode(query)}",
            self._create_base_request_body(settings),
        )
        finder_user = _find_nested_dict(response, "finderUser") or {}
        nickname = _first_text(finder_user, "nickname")
        account_id = _find_nested_text_excluding(response, {"userAttr"}, "finderUsername")
        if not nickname and not account_id:
            raise CollectorError("账号信息接口已返回，但没有找到可用的账号名。")
        logger.info("账号身份读取成功 account=%s account_label=%s account_id=%s", _account_label(settings), nickname or "-", _mask_identifier(account_id))
        return AccountIdentity(account_id=account_id, account_label=nickname)

    def prepare_capture(self, settings: MonitorSettings) -> CapturePreparationResult:
        logger.info("准备读取近期视频 account=%s", _account_label(settings))
        account = self._read_account_identity(settings)
        videos = self._fetch_all_videos_from_post_list(settings)
        preview_videos = [self._to_captured_video(item, account) for item in videos]
        preview_videos = [video for video in preview_videos if video is not None]
        if not preview_videos:
            logger.info("官网请求成功但没有发现数据 account=%s raw_count=%s", _account_label(settings), len(videos))
            return CapturePreparationResult(
                ok=True,
                message="官网请求成功，没发现数据。",
                account_id=account.account_id,
                account_label=account.account_label,
                videos=[],
            )
        logger.info("近期视频读取成功 account=%s videos=%s", account.account_label or _account_label(settings), len(preview_videos))
        return CapturePreparationResult(
            ok=True,
            message=f"成功读取 {len(preview_videos)} 条近期视频。",
            account_id=account.account_id,
            account_label=account.account_label,
            videos=preview_videos,
        )

    def capture(self, settings: MonitorSettings, selected_video_ids: list[str]) -> CaptureRunResult:
        logger.info("开始采集账号 account=%s selected_videos=%s", _account_label(settings), len(selected_video_ids))
        account = self._read_account_identity(settings)
        videos = self._fetch_all_videos_from_post_list(settings)
        selected = {item.strip() for item in selected_video_ids if item and item.strip()}
        target_items = [item for item in videos if item.object_id and (not selected or item.object_id in selected)]
        if not target_items:
            logger.warning(
                "已读取视频列表但未匹配到已选视频 account=%s selected=%s available=%s",
                account.account_label or _account_label(settings),
                len(selected),
                len(videos),
            )
            return CaptureRunResult(
                ok=False,
                message="未匹配到这次要采集的视频，请重新刷新视频列表后再选择。",
                account_id=account.account_id,
                account_label=account.account_label,
                videos=[],
            )

        captured: list[CapturedVideo] = []
        for item in target_items:
            logger.info(
                "开始读取视频明细 account=%s feed_id=%s title=%s",
                account.account_label or _account_label(settings),
                item.object_id,
                item.title,
            )
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

        logger.info("账号采集完成 account=%s captured=%s", account.account_label or _account_label(settings), len(captured))
        return CaptureRunResult(
            ok=True,
            message=f"成功采集 {len(captured)} 条视频数据。",
            account_id=account.account_id,
            account_label=account.account_label,
            videos=captured,
        )

    def _request_json(
        self,
        settings: MonitorSettings,
        path: str,
        body: dict[str, Any],
        *,
        allow_business_error: bool = False,
    ) -> dict[str, Any]:
        if not settings.session_cookie.strip():
            logger.warning("微信请求被跳过：Cookie 为空 path=%s account=%s", path, _account_label(settings))
            raise CollectorError("请先在设置里填写视频号后台请求的 Cookie，再开始采集。")

        parsed = parse.urlparse(settings.target_url.rstrip("/"))
        endpoint = f"{parsed.scheme}://{parsed.netloc}{path}"
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        timeout_seconds = max(5, settings.request_timeout_seconds)
        request_id = uuid.uuid4().hex[:8]
        started_at = time.perf_counter()
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
        logger.info(
            "微信请求开始 request_id=%s path=%s account=%s account_id=%s timeout=%ss cookie=%s body=%s",
            request_id,
            path,
            _account_label(settings),
            _mask_identifier(settings.selected_account_id),
            timeout_seconds,
            _cookie_summary(settings.session_cookie),
            _body_summary(body),
        )
        try:
            with _urlopen_direct(req, timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
                http_status = getattr(response, "status", None)
        except urlerror.HTTPError as exc:
            raw_error = _read_http_error_body(exc)
            elapsed_ms = _elapsed_ms(started_at)
            hint = _http_error_hint(exc.code, raw_error)
            logger.error(
                "微信请求 HTTP 错误 request_id=%s path=%s status=%s reason=%s elapsed_ms=%s hint=%s body=%s",
                request_id,
                path,
                exc.code,
                exc.reason,
                elapsed_ms,
                hint or "-",
                _preview_text(raw_error),
            )
            raise CollectorError(f"接口请求失败：{path}，HTTP {exc.code}{_format_hint(hint)}") from exc
        except urlerror.URLError as exc:
            elapsed_ms = _elapsed_ms(started_at)
            reason = getattr(exc, "reason", exc)
            if _is_timeout_error(reason):
                logger.error(
                    "微信请求超时 request_id=%s path=%s timeout=%ss elapsed_ms=%s reason=%s",
                    request_id,
                    path,
                    timeout_seconds,
                    elapsed_ms,
                    reason,
                )
                raise CollectorError(f"接口请求超时：{path}，已等待 {timeout_seconds} 秒，请检查网络或调大请求超时。") from exc
            logger.error(
                "微信请求网络错误 request_id=%s path=%s elapsed_ms=%s reason=%s",
                request_id,
                path,
                elapsed_ms,
                reason,
            )
            raise CollectorError(f"接口请求失败：{path}，网络错误：{reason}") from exc
        except (TimeoutError, socket.timeout) as exc:
            elapsed_ms = _elapsed_ms(started_at)
            logger.error(
                "微信请求超时 request_id=%s path=%s timeout=%ss elapsed_ms=%s",
                request_id,
                path,
                timeout_seconds,
                elapsed_ms,
            )
            raise CollectorError(f"接口请求超时：{path}，已等待 {timeout_seconds} 秒，请检查网络或调大请求超时。") from exc
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = _elapsed_ms(started_at)
            logger.exception("微信请求异常 request_id=%s path=%s elapsed_ms=%s", request_id, path, elapsed_ms)
            raise CollectorError(f"接口请求失败：{path}，{exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error(
                "微信请求返回非 JSON request_id=%s path=%s status=%s elapsed_ms=%s body=%s",
                request_id,
                path,
                http_status,
                _elapsed_ms(started_at),
                _preview_text(raw),
            )
            raise CollectorError(f"接口返回不是合法 JSON：{path}，可能是登录态失效或微信后台返回了 HTML。") from exc

        err_code = data.get("errCode")
        err_msg = data.get("errMsg")
        if err_code not in (None, 0, "0"):
            hint = _business_error_hint(err_code, err_msg)
            log = logger.info if allow_business_error else logger.warning
            log(
                "微信请求业务状态 request_id=%s path=%s status=%s err_code=%s err_msg=%s elapsed_ms=%s hint=%s allowed=%s",
                request_id,
                path,
                http_status,
                err_code,
                err_msg,
                _elapsed_ms(started_at),
                hint or "-",
                allow_business_error,
            )
            if allow_business_error:
                return data
            raise CollectorError(_format_business_error_message(path, err_code, err_msg, hint))
        logger.info(
            "微信请求成功 request_id=%s path=%s status=%s err_code=%s elapsed_ms=%s bytes=%s",
            request_id,
            path,
            http_status,
            err_code,
            _elapsed_ms(started_at),
            len(raw),
        )
        return data

    def _request_json_get(self, settings: MonitorSettings, path: str, query: dict[str, Any]) -> dict[str, Any]:
        if not settings.session_cookie.strip():
            logger.warning("微信 GET 请求被跳过：Cookie 为空 path=%s account=%s", path, _account_label(settings))
            raise CollectorError("请先在设置里填写视频号后台请求的 Cookie，再开始采集。")

        parsed = parse.urlparse(settings.target_url.rstrip("/"))
        endpoint = f"{parsed.scheme}://{parsed.netloc}{path}?{parse.urlencode(query)}"
        timeout_seconds = max(5, settings.request_timeout_seconds)
        request_id = uuid.uuid4().hex[:8]
        started_at = time.perf_counter()
        headers = {
            "accept": "application/json, text/plain, */*",
            "cookie": settings.session_cookie.strip(),
            "referer": _platform_url(settings),
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
            ),
        }
        req = request.Request(endpoint, headers=headers, method="GET")
        logger.info(
            "微信 GET 请求开始 request_id=%s path=%s account=%s timeout=%ss cookie=%s query=%s",
            request_id,
            path,
            _account_label(settings),
            timeout_seconds,
            _cookie_summary(settings.session_cookie),
            {key: query.get(key) for key in ("_rid", "_pageUrl")},
        )
        try:
            with _urlopen_direct(req, timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
                http_status = getattr(response, "status", None)
        except urlerror.HTTPError as exc:
            raw_error = _read_http_error_body(exc)
            hint = _http_error_hint(exc.code, raw_error)
            logger.error(
                "微信 GET 请求 HTTP 错误 request_id=%s path=%s status=%s reason=%s elapsed_ms=%s hint=%s body=%s",
                request_id,
                path,
                exc.code,
                exc.reason,
                _elapsed_ms(started_at),
                hint or "-",
                _preview_text(raw_error),
            )
            raise CollectorError(f"接口请求失败：{path}，HTTP {exc.code}{_format_hint(hint)}") from exc
        except urlerror.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if _is_timeout_error(reason):
                logger.error(
                    "微信 GET 请求超时 request_id=%s path=%s timeout=%ss elapsed_ms=%s reason=%s",
                    request_id,
                    path,
                    timeout_seconds,
                    _elapsed_ms(started_at),
                    reason,
                )
                raise CollectorError(f"接口请求超时：{path}，已等待 {timeout_seconds} 秒，请检查网络或调大请求超时。") from exc
            logger.error(
                "微信 GET 请求网络错误 request_id=%s path=%s elapsed_ms=%s reason=%s",
                request_id,
                path,
                _elapsed_ms(started_at),
                reason,
            )
            raise CollectorError(f"接口请求失败：{path}，网络错误：{reason}") from exc
        except (TimeoutError, socket.timeout) as exc:
            logger.error(
                "微信 GET 请求超时 request_id=%s path=%s timeout=%ss elapsed_ms=%s",
                request_id,
                path,
                timeout_seconds,
                _elapsed_ms(started_at),
            )
            raise CollectorError(f"接口请求超时：{path}，已等待 {timeout_seconds} 秒，请检查网络或调大请求超时。") from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("微信 GET 请求异常 request_id=%s path=%s elapsed_ms=%s", request_id, path, _elapsed_ms(started_at))
            raise CollectorError(f"接口请求失败：{path}，{exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error(
                "微信 GET 请求返回非 JSON request_id=%s path=%s status=%s elapsed_ms=%s body=%s",
                request_id,
                path,
                http_status,
                _elapsed_ms(started_at),
                _preview_text(raw),
            )
            raise CollectorError(f"接口返回不是合法 JSON：{path}，可能是登录态失效或微信后台返回了 HTML。") from exc

        err_code = data.get("errCode")
        err_msg = data.get("errMsg")
        if err_code not in (None, 0, "0"):
            hint = _business_error_hint(err_code, err_msg)
            logger.warning(
                "微信 GET 请求业务错误 request_id=%s path=%s status=%s err_code=%s err_msg=%s elapsed_ms=%s hint=%s",
                request_id,
                path,
                http_status,
                err_code,
                err_msg,
                _elapsed_ms(started_at),
                hint or "-",
            )
            raise CollectorError(_format_business_error_message(path, err_code, err_msg, hint))
        logger.info(
            "微信 GET 请求成功 request_id=%s path=%s status=%s err_code=%s elapsed_ms=%s bytes=%s",
            request_id,
            path,
            http_status,
            err_code,
            _elapsed_ms(started_at),
            len(raw),
        )
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
        logger.info(
            "开始读取视频列表 account=%s start_ts=%s end_ts=%s page_size=%s",
            _account_label(settings),
            start_ts,
            end_ts,
            page_size,
        )
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
            logger.info(
                "视频列表分页完成 account=%s page=%s page_items=%s total_count=%s accumulated=%s",
                _account_label(settings),
                current_page,
                len(page_items),
                total_count,
                len(items),
            )
            if len(page_items) < page_size:
                break
            current_page += 1
        if not items:
            logger.info("官网请求成功但视频列表为空 account=%s", _account_label(settings))
        return items

    def _fetch_detail_metrics(self, settings: MonitorSettings, feed_id: str) -> VideoMetrics:
        logger.info("开始读取视频明细指标 account=%s feed_id=%s", _account_label(settings), feed_id)
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
        logger.info("视频明细指标返回 account=%s feed_id=%s tab_count=%s", _account_label(settings), feed_id, len(feed_data))
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


def _account_label(settings: MonitorSettings) -> str:
    return settings.selected_account_label or settings.account_label_hint or settings.selected_account_id or "未命名账号"


def _platform_url(settings: MonitorSettings) -> str:
    parsed = parse.urlparse(settings.target_url.rstrip("/"))
    return f"{parsed.scheme}://{parsed.netloc}/platform"


def _first_text(source: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value is not None and not isinstance(value, (dict, list, tuple, set)):
            text = str(value).strip()
            if text:
                return text
    return None


def _find_nested_dict(source: Any, key: str) -> dict[str, Any] | None:
    if isinstance(source, dict):
        value = source.get(key)
        if isinstance(value, dict):
            return value
        for child in source.values():
            found = _find_nested_dict(child, key)
            if found is not None:
                return found
    elif isinstance(source, list):
        for child in source:
            found = _find_nested_dict(child, key)
            if found is not None:
                return found
    return None


def _find_nested_text(source: Any, *keys: str) -> str | None:
    if isinstance(source, dict):
        direct = _first_text(source, *keys)
        if direct:
            return direct
        for child in source.values():
            found = _find_nested_text(child, *keys)
            if found:
                return found
    elif isinstance(source, list):
        for child in source:
            found = _find_nested_text(child, *keys)
            if found:
                return found
    return None


def _find_nested_text_excluding(source: Any, excluded_keys: set[str], *keys: str) -> str | None:
    if isinstance(source, dict):
        direct = _first_text(source, *keys)
        if direct:
            return direct
        for key, child in source.items():
            if key in excluded_keys:
                continue
            found = _find_nested_text_excluding(child, excluded_keys, *keys)
            if found:
                return found
    elif isinstance(source, list):
        for child in source:
            found = _find_nested_text_excluding(child, excluded_keys, *keys)
            if found:
                return found
    return None


def _urlopen_direct(req: request.Request, timeout_seconds: int):
    opener = request.build_opener(request.ProxyHandler({}))
    return opener.open(req, timeout=timeout_seconds)


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _is_timeout_error(error: Any) -> bool:
    return isinstance(error, (TimeoutError, socket.timeout)) or "timed out" in str(error).lower()


def _read_http_error_body(exc: urlerror.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _preview_text(value: Any, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _mask_identifier(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    if len(text) <= 8:
        return f"{text[:2]}***"
    return f"{text[:4]}***{text[-4:]}"


def _cookie_summary(cookie: str) -> str:
    text = str(cookie or "").strip()
    if not text:
        return "empty"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    parts = {}
    for item in text.split(";"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        parts[key.strip().lower()] = value.strip()
    wxuin = _mask_identifier(parts.get("wxuin"))
    has_sessionid = "yes" if parts.get("sessionid") else "no"
    return f"len={len(text)} sha256={digest} wxuin={wxuin} sessionid={has_sessionid}"


def _body_summary(body: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = (
        "currentPage",
        "pageSize",
        "feedId",
        "startTime",
        "endTime",
        "startTs",
        "endTs",
        "interval",
        "sort",
        "order",
        "scene",
        "reqScene",
    )
    return {key: body.get(key) for key in allowed_keys if key in body}


def _http_error_hint(status_code: int, raw_body: str = "") -> str | None:
    if status_code in {401, 403}:
        return "登录态可能失效，请重新复制该账号 Cookie。"
    if status_code == 429:
        return "请求过于频繁，建议降低采集频率或稍后重试。"
    if status_code >= 500:
        return "微信服务端异常或临时不可用。"
    if _looks_like_auth_error(raw_body):
        return "返回内容疑似登录态失效，请重新复制该账号 Cookie。"
    return None


def _business_error_hint(err_code: Any, err_msg: Any) -> str | None:
    text = f"{err_code} {err_msg or ''}"
    if str(err_code) in {"300334", "300342"}:
        return "Cookie 可能已失效，或当前 Cookie 不属于这个视频号，请重新复制该账号后台 Cookie。"
    if _looks_like_auth_error(text):
        return "登录态/Cookie 可能无效或过期，请重新复制该账号 Cookie。"
    if "频繁" in text or "rate" in text.lower() or str(err_code) in {"429", "-200010"}:
        return "请求可能过于频繁，建议降低采集频率或稍后重试。"
    if "权限" in text or "permission" in text.lower() or "forbidden" in text.lower():
        return "当前 Cookie 对该账号或接口可能没有权限。"
    return None


def _looks_like_auth_error(value: Any) -> bool:
    text = str(value or "").lower()
    keywords = (
        "cookie",
        "session",
        "token",
        "login",
        "auth",
        "unauthorized",
        "invalid",
        "expired",
        "登录",
        "登陆",
        "过期",
        "鉴权",
        "认证",
        "未登录",
    )
    return any(keyword in text for keyword in keywords)


def _format_hint(hint: str | None) -> str:
    return f"，{hint}" if hint else ""


def _format_business_error_message(path: str, err_code: Any, err_msg: Any, hint: str | None) -> str:
    detail = str(err_msg or "").strip()
    suffix = f"：{detail}" if detail else ""
    return f"{_interface_name(path)} 连接成功，但微信返回业务码 {err_code}{suffix}{_format_hint(hint)}"


def _interface_name(path: str) -> str:
    clean_path = str(path or "").split("?", 1)[0].rstrip("/")
    return clean_path.rsplit("/", 1)[-1] or clean_path or "接口"


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
