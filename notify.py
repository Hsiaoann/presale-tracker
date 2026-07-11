# -*- coding: utf-8 -*-
"""
訊息格式化與推播。

⚠️ 關於 LINE Notify：LINE 官方已於 2025 年 3 月底終止 LINE Notify 服務。
   因此本檔案同時提供 LINE Messaging API 版本（官方建議的替代方案）。
   兩種擇一使用，由環境變數決定。詳見 README。

   - 若你已有舊的 LINE Notify token 且仍可用，設 NOTIFY_METHOD=line_notify
   - 建議改用 Messaging API：設 NOTIFY_METHOD=line_messaging
   - 想先本機測試不推播：設 NOTIFY_METHOD=console（只印在畫面上）
"""
import os
import requests
from typing import List, Tuple
from models import Listing, group_by_region


def format_message(city: str, region_groups: dict,
                   new_listings: List[Listing],
                   status_changed: List[Tuple[Listing, str]]) -> str:
    """把某城市的新案與狀態變化，組成依區域分組的通知文字。"""
    if not new_listings and not status_changed:
        return ""

    lines = [f"🏙 {city}"]

    if new_listings:
        grouped = group_by_region(new_listings, region_groups)
        # 依分組名稱排序，讓每天輸出順序穩定
        for group_name in sorted(grouped.keys()):
            items = grouped[group_name]
            lines.append(f"\n【{group_name}】新案 {len(items)} 筆")
            for lst in items:
                parts = [f"・{lst.name}"]
                if lst.region:
                    parts.append(f"（{lst.region}）")
                if lst.price:
                    parts.append(f" {lst.price}")
                if lst.status:
                    parts.append(f" [{lst.status}]")
                lines.append("".join(parts))
                if lst.url:
                    lines.append(f"  {lst.url}")

    if status_changed:
        lines.append("\n【狀態變化｜可能開始銷售】")
        for lst, old_status in status_changed:
            lines.append(
                f"・{lst.name}（{lst.region}）"
                f" {old_status or '—'} → {lst.status}"
            )
            if lst.url:
                lines.append(f"  {lst.url}")

    return "\n".join(lines)


def send(message: str) -> None:
    """依 NOTIFY_METHOD 推播訊息。"""
    if not message.strip():
        print("（無新案，不推播）")
        return

    method = os.environ.get("NOTIFY_METHOD", "console")

    if method == "console":
        print("─" * 40)
        print(message)
        print("─" * 40)
        return

    if method == "line_notify":
        token = os.environ.get("LINE_NOTIFY_TOKEN", "")
        if not token:
            print("[warn] 未設定 LINE_NOTIFY_TOKEN，改印在畫面")
            print(message)
            return
        _send_line_notify(token, message)
        return

    if method == "line_messaging":
        token = os.environ.get("LINE_CHANNEL_TOKEN", "")
        user_id = os.environ.get("LINE_USER_ID", "")
        if not token or not user_id:
            print("[warn] 未設定 LINE_CHANNEL_TOKEN / LINE_USER_ID，改印在畫面")
            print(message)
            return
        _send_line_messaging(token, user_id, message)
        return

    print(f"[warn] 未知的 NOTIFY_METHOD={method}，改印在畫面")
    print(message)


def _send_line_notify(token: str, message: str) -> None:
    """LINE Notify（已停止服務，僅為相容保留）。訊息過長會分段。"""
    for chunk in _chunk(message, 900):
        resp = requests.post(
            "https://notify-api.line.me/api/notify",
            headers={"Authorization": f"Bearer {token}"},
            data={"message": "\n" + chunk},
            timeout=20,
        )
        if resp.status_code != 200:
            print(f"[line_notify] 推播失敗 {resp.status_code}: {resp.text}")


def _send_line_messaging(token: str, user_id: str, message: str) -> None:
    """LINE Messaging API（官方建議方案）。單則上限 5000 字，這裡保守分段。"""
    for chunk in _chunk(message, 4500):
        resp = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"to": user_id, "messages": [{"type": "text", "text": chunk}]},
            timeout=20,
        )
        if resp.status_code != 200:
            print(f"[line_messaging] 推播失敗 {resp.status_code}: {resp.text}")


def _chunk(text: str, size: int):
    """把長訊息切段，盡量在換行處切。"""
    while text:
        if len(text) <= size:
            yield text
            return
        cut = text.rfind("\n", 0, size)
        if cut == -1:
            cut = size
        yield text[:cut]
        text = text[cut:].lstrip("\n")
