from __future__ import annotations

import threading
import time
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

from sph_flow.collector import CollectorError, WeixinChannelCollector
from sph_flow.models import AccountConfig, CapturePreparationResult, CaptureRunResult, MonitorSettings, format_datetime_text, now_display_time
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
            "accountStatuses": self._build_account_statuses(settings),
            "recentSnapshots": [item.to_dict(camel=True) for item in recent],
            "hasCaptureHistory": bool(recent),
        }

    def prepare_capture(self) -> CapturePreparationResult:
        settings = self.get_settings()
        accounts = _get_configured_accounts(settings)
        if len(accounts) != 1:
            raise RuntimeError("多账号模式请使用 prepare_capture_accounts。")
        account_settings = _settings_for_account(settings, accounts[0])
        try:
            return self.collector.prepare_capture(account_settings)
        except CollectorError as exc:
            return CapturePreparationResult(ok=False, message=str(exc), videos=[])

    def prepare_capture_accounts(self, account_keys: list[str] | None = None) -> dict[str, Any]:
        settings = self.get_settings()
        accounts = _get_configured_accounts(settings)
        if account_keys:
            wanted = {str(key).strip() for key in account_keys if str(key).strip()}
            accounts = [account for account in accounts if account.key in wanted]
        if not accounts:
            return {"ok": False, "message": "请先添加至少一个账号 Cookie。", "previews": []}

        previews = []
        for account in accounts:
            account_settings = _settings_for_account(settings, account)
            try:
                preview = self.collector.prepare_capture(account_settings)
            except CollectorError as exc:
                preview = CapturePreparationResult(ok=False, message=str(exc), videos=[])
            resolved_label = preview.account_label or account.account_label or account.account_label_hint or account.key
            previews.append(
                {
                    "accountKey": account.key,
                    "accountId": preview.account_id or account.account_id,
                    "accountLabel": resolved_label,
                    "message": preview.message,
                    "ok": preview.ok,
                    "savedSelectedVideoIds": account.selected_video_ids,
                    "videos": [video.to_dict(camel=True) for video in preview.videos],
                }
            )

        return {
            "ok": bool(previews),
            "message": f"已读取 {len(previews)} 个账号。",
            "previews": previews,
        }

    def start_capture_session(self, selected_accounts: list[dict[str, Any]] | list[str]) -> dict[str, Any]:
        selections = _normalize_account_selections(selected_accounts)
        if not selections:
            raise ValueError("请至少选择一个要采集的视频。")

        settings = self.get_settings()
        accounts = _get_configured_accounts(settings)
        account_by_key = {account.key: account for account in accounts}
        unknown_keys = sorted(key for key in selections if key not in account_by_key)
        if unknown_keys:
            raise ValueError(f"账号配置不存在：{', '.join(unknown_keys)}")

        updated_accounts: list[AccountConfig] = []
        for account in accounts:
            if account.key not in selections:
                updated_accounts.append(account)
                continue

            selected_video_ids = selections[account.key]
            if selected_video_ids:
                account_settings = _settings_for_account(settings, account)
                preview = self.collector.prepare_capture(account_settings)
                if not preview.ok:
                    raise RuntimeError(f"{account.display_label}：{preview.message}")
                updated_accounts.append(
                    replace(
                        account,
                        account_id=preview.account_id or account.account_id,
                        account_label=preview.account_label or account.account_label or account.account_label_hint,
                        selected_video_ids=selected_video_ids,
                        capture_enabled=True,
                    )
                )

        settings = self.save_settings(
            {
                "capture_paused": False,
                "accounts": [account.to_dict() for account in updated_accounts],
            }
        )
        result = self.run_capture(account_keys=list(selections))
        return {
            "settings": settings.to_dict(camel=True),
            "result": result.to_dict(camel=True),
        }

    def run_capture(self, account_keys: list[str] | None = None) -> CaptureRunResult:
        if not self._capture_lock.acquire(blocking=False):
            raise RuntimeError("后台采集正在进行中，请稍后再试。")

        started_at = now_display_time()
        settings = self.get_settings()
        accounts = _get_selected_accounts(settings)
        if account_keys:
            wanted = {str(key).strip() for key in account_keys if str(key).strip()}
            accounts = [account for account in accounts if account.key in wanted]
        selected_video_count = sum(len(account.selected_video_ids) for account in accounts)
        self.storage.save_status(
            {
                "last_run_at": started_at,
                "last_error": None,
                "last_message": f"正在采集 {len(accounts)} 个账号的 {selected_video_count} 条视频..." if accounts else "正在采集...",
                "account_label": _format_account_scope(accounts),
            }
        )

        try:
            if not accounts:
                raise RuntimeError("尚未选择任何账号视频，请点击开始采集后先勾选要采集的视频。")

            captured_videos = []
            errors = []
            for account in accounts:
                account_settings = _settings_for_account(settings, account)
                try:
                    result = self.collector.capture(account_settings, account.selected_video_ids)
                    if not result.ok:
                        raise RuntimeError(result.message)
                    account_label = result.account_label or account.account_label or account.account_label_hint or None
                    account_id = result.account_id or account.account_id or None
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
                    captured_videos.extend(result.videos)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{account.display_label}：{exc}")

            if errors and not captured_videos:
                raise RuntimeError("；".join(errors))

            self.storage.prune_expired_snapshots(settings.retention_days)
            message = f"成功采集 {len(accounts) - len(errors)} / {len(accounts)} 个账号，{len(captured_videos)} 条视频数据。"
            self.storage.save_status(
                {
                    "last_success_at": now_display_time(),
                    "last_error": "；".join(errors) if errors else None,
                    "last_message": message,
                    "account_label": _format_account_scope(accounts),
                }
            )
            return CaptureRunResult(
                ok=True,
                message=message,
                account_id=None,
                account_label=_format_account_scope(accounts),
                videos=captured_videos,
            )
        except Exception as exc:  # noqa: BLE001
            self.storage.save_status(
                {
                    "last_error": str(exc),
                    "last_message": None,
                    "account_label": _format_account_scope(accounts),
                }
            )
            raise
        finally:
            self._capture_lock.release()

    def set_capture_paused(self, paused: bool) -> MonitorSettings:
        return self.save_settings({"capture_paused": bool(paused)})

    def set_account_capture_enabled(self, account_key: str, enabled: bool) -> MonitorSettings:
        settings = self.get_settings()
        updated_accounts = []
        matched = False
        for account in _get_configured_accounts(settings):
            if account.key == account_key:
                matched = True
                updated_accounts.append(replace(account, capture_enabled=bool(enabled)))
            else:
                updated_accounts.append(account)
        if not matched:
            raise ValueError("账号配置不存在。")
        return self.save_settings(
            {
                "capture_paused": False,
                "accounts": [account.to_dict() for account in updated_accounts],
            }
        )

    def _build_account_statuses(self, settings: MonitorSettings) -> list[dict[str, Any]]:
        videos = self.storage.list_videos()
        statuses = []
        for account in _get_configured_accounts(settings):
            selected_count = len(_normalize_selected_video_ids(account.selected_video_ids))
            matched_videos = [video for video in videos if _video_matches_account(video, account)]
            latest_video = max(matched_videos, key=lambda video: video.last_captured_at or now_display_time(), default=None)
            if selected_count == 0:
                status_text = "未选择视频"
            elif account.capture_enabled:
                status_text = "后台采集中"
            else:
                status_text = "已暂停"
            statuses.append(
                {
                    "accountKey": account.key,
                    "accountId": account.account_id,
                    "accountLabel": account.display_label,
                    "captureEnabled": account.capture_enabled,
                    "selectedVideoCount": selected_count,
                    "lastCapturedAt": format_datetime_text(latest_video.last_captured_at) if latest_video else None,
                    "statusText": status_text,
                }
            )
        return statuses

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
            if not _get_selected_accounts(settings):
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


def _get_configured_accounts(settings: MonitorSettings) -> list[AccountConfig]:
    accounts = [account for account in settings.accounts if account.session_cookie.strip()]
    if accounts:
        return accounts
    if settings.session_cookie.strip():
        return [
            AccountConfig(
                key="default",
                account_id=settings.selected_account_id,
                account_label=settings.selected_account_label,
                session_cookie=settings.session_cookie,
                account_label_hint=settings.account_label_hint,
                selected_video_ids=settings.selected_video_ids,
            )
        ]
    return []


def _get_selected_accounts(settings: MonitorSettings) -> list[AccountConfig]:
    return [
        account
        for account in _get_configured_accounts(settings)
        if account.capture_enabled and _normalize_selected_video_ids(account.selected_video_ids)
    ]


def _settings_for_account(settings: MonitorSettings, account: AccountConfig) -> MonitorSettings:
    return replace(
        settings,
        selected_video_ids=_normalize_selected_video_ids(account.selected_video_ids),
        selected_account_id=account.account_id,
        selected_account_label=account.account_label,
        session_cookie=account.session_cookie,
        account_label_hint=account.account_label_hint,
    )


def _format_account_scope(accounts: list[AccountConfig]) -> str | None:
    if not accounts:
        return None
    if len(accounts) == 1:
        return accounts[0].display_label
    return f"{len(accounts)} 个账号"


def _video_matches_account(video: Any, account: AccountConfig) -> bool:
    if account.account_id and video.account_id == account.account_id:
        return True
    labels = {account.account_label, account.account_label_hint, account.display_label}
    return bool(video.account_label and video.account_label in labels)


def _normalize_account_selections(selected_accounts: list[dict[str, Any]] | list[str] | None) -> dict[str, list[str]]:
    if not selected_accounts:
        return {}
    if all(isinstance(item, str) for item in selected_accounts):
        return {"default": _normalize_selected_video_ids(selected_accounts)}  # Backward compatibility.

    selections: dict[str, list[str]] = {}
    for index, item in enumerate(selected_accounts):
        if not isinstance(item, dict):
            continue
        key = str(item.get("accountKey") or item.get("key") or f"account-{index + 1}").strip()
        video_ids = _normalize_selected_video_ids(item.get("selectedVideoIds") or item.get("selected_video_ids") or [])
        if key and video_ids:
            selections[key] = video_ids
    return selections


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
