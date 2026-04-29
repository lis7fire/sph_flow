from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from sph_flow.models import VideoSnapshot, format_datetime_text


def build_snapshots_workbook(rows: list[VideoSnapshot]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/styles.xml", _styles_xml())
        archive.writestr("xl/worksheets/sheet1.xml", _sheet_xml(rows))
    return buffer.getvalue()


def _content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""


def _root_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""


def _workbook_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="snapshots" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""


def _workbook_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><name val="Calibri"/></font>
  </fonts>
  <fills count="2">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
  </fills>
  <borders count="1">
    <border><left/><right/><top/><bottom/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
  </cellXfs>
</styleSheet>"""


def _sheet_xml(rows: list[VideoSnapshot]) -> str:
    headers = [
        "账号",
        "标题/文案",
        "发布时间",
        "采集时间",
        "播放量",
        "点赞量",
        "评论量",
        "分享量",
        "关注量",
        "转发到聊天和朋友圈",
        "设为铃声",
        "设为状态",
        "设为朋友圈封面",
        "完播率",
        "平均播放时长(秒)",
        "用户ID",
        "导出ID",
        "视频ID",
    ]
    all_rows = [headers]
    for row in rows:
        all_rows.append(
            [
                row.account_label or "",
                row.description or row.video_title,
                _format_timestamp(row.publish_time),
                _format_timestamp(row.captured_at),
                row.metrics.play_count,
                row.metrics.like_count,
                row.metrics.comment_count,
                row.metrics.share_count,
                row.metrics.follow_count,
                row.metrics.forward_chat_count,
                row.metrics.ringtone_count,
                row.metrics.status_count,
                row.metrics.cover_count,
                row.metrics.completion_rate,
                row.metrics.avg_play_time_seconds,
                row.log_finder_id or "",
                row.export_id or "",
                row.video_id,
            ]
        )

    row_xml = []
    for row_index, row in enumerate(all_rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            cell_ref = f"{_column_name(col_index)}{row_index}"
            style = ' s="1"' if row_index == 1 else ""
            if isinstance(value, (int, float)) and row_index > 1:
                cells.append(f'<c r="{cell_ref}"{style}><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{cell_ref}" t="inlineStr"{style}><is><t>{escape(str(value))}</t></is></c>')
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    return (
        """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>"""
        """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">"""
        """<sheetViews><sheetView workbookViewId="0"/></sheetViews>"""
        """<sheetFormatPr defaultRowHeight="15"/>"""
        """<cols><col min="1" max="1" width="18" customWidth="1"/>"""
        """<col min="2" max="2" width="44" customWidth="1"/>"""
        """<col min="3" max="4" width="22" customWidth="1"/>"""
        """<col min="5" max="15" width="16" customWidth="1"/>"""
        """<col min="16" max="18" width="22" customWidth="1"/></cols>"""
        f"""<sheetData>{"".join(row_xml)}</sheetData>"""
        """</worksheet>"""
    )


def _column_name(index: int) -> str:
    letters = []
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def _format_timestamp(value: object) -> str:
    return format_datetime_text(value) or ""
