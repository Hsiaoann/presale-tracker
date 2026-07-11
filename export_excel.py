# -*- coding: utf-8 -*-
"""把 seen_listings.json 匯出成 Excel 清單（每日排程自動執行）。"""
import json
import os
from datetime import datetime, timezone, timedelta

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

from config import CITIES

STATE_FILE = "seen_listings.json"
OUTPUT_FILE = "listings.xlsx"
TW = timezone(timedelta(hours=8))

SOURCE_NAME = {"rakuya": "樂屋網", "housefun": "好房網"}


def build_region_lookup():
    lookup = {}
    for city, cfg in CITIES.items():
        for group, regions in cfg.get("region_groups", {}).items():
            for r in regions:
                lookup[(city, r)] = group
    return lookup


def main():
    if not os.path.exists(STATE_FILE):
        print("找不到 seen_listings.json，略過匯出")
        return
    with open(STATE_FILE, encoding="utf-8") as f:
        seen = json.load(f)
    if not seen:
        print("清單為空，略過匯出")
        return

    lookup = build_region_lookup()
    rows = []
    for item in seen.values():
        city = item.get("city", "")
        region = item.get("region", "")
        rows.append({
            "城市": city.replace("_青埔", "（青埔）"),
            "區域分組": lookup.get((city, region), "其他"),
            "行政區": region,
            "案名": item.get("name", ""),
            "單價": item.get("price", ""),
            "坪數房型": item.get("rooms", ""),
            "地址": item.get("address", ""),
            "狀態": item.get("status", ""),
            "來源": SOURCE_NAME.get(item.get("source", ""), item.get("source", "")),
            "首次發現": item.get("first_seen", ""),
        })

    rows.sort(key=lambda r: (r["城市"], r["區域分組"], r["行政區"], r["案名"]))

    wb = Workbook()
    ws = wb.active
    ws.title = "預售案清單"
    headers = ["城市", "區域分組", "行政區", "案名", "單價",
               "坪數房型", "地址", "狀態", "來源", "首次發現"]

    hf = Font(name="Arial", bold=True, color="FFFFFF")
    fill = PatternFill("solid", fgColor="4472C4")
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = hf
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    body = Font(name="Arial")
    for i, r in enumerate(rows, start=2):
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=i, column=c, value=r[h])
            cell.font = body

    widths = {"城市": 14, "區域分組": 18, "行政區": 10, "案名": 24, "單價": 15,
              "坪數房型": 20, "地址": 34, "狀態": 10, "來源": 10, "首次發現": 12}
    for c, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(c)].width = widths[h]

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"

    note = (f"最後更新：{datetime.now(TW).strftime('%Y-%m-%d %H:%M')}（台灣時間）　"
            f"共 {len(rows)} 筆　資料來源：好房網、樂屋網")
    nc = ws.cell(row=len(rows) + 3, column=1, value=note)
    nc.font = Font(name="Arial", italic=True, size=9, color="808080")

    wb.save(OUTPUT_FILE)
    print(f"已匯出 {OUTPUT_FILE}：{len(rows)} 筆")


if __name__ == "__main__":
    main()
