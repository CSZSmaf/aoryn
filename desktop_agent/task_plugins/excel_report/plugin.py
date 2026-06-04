from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from desktop_agent.plugin_runtime import PluginManifest, PluginRunResult
from desktop_agent.task_plugins import office_common


_EXCEL_TERMS = ("excel", "xlsx", "表格", "工作簿", "Excel")
_REPORT_TERMS = ("报表", "图表", "趋势", "销售", "利润", "分析", "report", "chart", "sales")

_ROWS: list[list[Any]] = [
    ["月份", "收入", "成本", "利润"],
    ["1月", 128000, 76000, 52000],
    ["2月", 142000, 82000, 60000],
    ["3月", 151000, 87000, 64000],
    ["4月", 168000, 93000, 75000],
    ["5月", 181000, 101000, 80000],
    ["6月", 196000, 108000, 88000],
]


def match_task(task: str, *, manifest: PluginManifest, config: Any | None = None) -> bool:
    text = str(task or "")
    lowered = text.lower()
    has_excel = any(term.lower() in lowered for term in _EXCEL_TERMS)
    has_work = any(term in text or term.lower() in lowered for term in _REPORT_TERMS)
    return has_excel and has_work


def status(*, manifest: PluginManifest, config: Any | None = None) -> dict[str, Any]:
    return office_common.office_status("excel", config=config, file_label="an .xlsx workbook")


def run_task(
    task: str,
    context: Any,
    *,
    manifest: PluginManifest,
    config: Any | None = None,
) -> PluginRunResult:
    output_dir = office_common.resolve_output_dir(context)
    workbook_path = output_dir / "Aoryn_Excel插件销售分析.xlsx"
    chart_path = output_dir / "Aoryn_Excel插件销售趋势.png"
    csv_path = output_dir / "Aoryn_Excel插件销售数据.csv"
    actions = office_common.emit(context, "Excel 插件正在生成销售数据工作簿和趋势图")

    executable = office_common.find_office_executable("excel", config) if _prefers_real_office(task) else None
    mode = "标准 XLSX 文件生成"
    com_error: str | None = None
    if executable is not None:
        try:
            _write_with_excel_com(workbook_path, chart_path)
            mode = f"Excel COM 自动化：{executable}"
        except Exception as exc:
            com_error = str(exc)
            office_common.write_basic_xlsx(workbook_path, "Sales", _ROWS)
            _draw_chart(chart_path)
    else:
        office_common.write_basic_xlsx(workbook_path, "Sales", _ROWS)
        _draw_chart(chart_path)

    _write_csv(csv_path)
    for path in (workbook_path, chart_path, csv_path):
        office_common.copy_to_run_dir(path, context)

    report_path = office_common.write_text_artifact(
        context,
        "Aoryn_Excel插件报告.md",
        _report(task=task, mode=mode, workbook=workbook_path, chart=chart_path, csv_file=csv_path, com_error=com_error),
    )
    office_common.open_artifacts(context, (workbook_path, chart_path, report_path))

    artifacts = [workbook_path.name, chart_path.name, csv_path.name, report_path.name]
    answer = (
        "✅ Excel 插件任务已完成：已生成销售数据工作簿、趋势图、CSV 数据和 Markdown 报告。\n\n"
        f"执行方式：{mode}\n"
        f"工作簿：{workbook_path}\n"
        f"趋势图：{chart_path}\n"
        f"报告：{report_path}"
    )
    return PluginRunResult(
        completed=True,
        headline="Excel 插件已完成：生成销售报表和趋势图",
        answer=answer,
        actions=actions,
        artifacts=artifacts,
    )


def _write_with_excel_com(workbook_path: Path, chart_path: Path) -> None:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    excel = None
    workbook = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        workbook = excel.Workbooks.Add()
        sheet = workbook.Worksheets(1)
        sheet.Name = "Sales"
        for row_index, row in enumerate(_ROWS, start=1):
            for col_index, value in enumerate(row, start=1):
                sheet.Cells(row_index, col_index).Value = value
        sheet.Range("A1:D1").Font.Bold = True
        sheet.Columns("A:D").AutoFit()
        chart_shape = sheet.Shapes.AddChart2(201, 51, 330, 25, 560, 320)
        chart = chart_shape.Chart
        chart.SetSourceData(sheet.Range("A1:D7"))
        chart.HasTitle = True
        chart.ChartTitle.Text = "Aoryn Excel Plugin - Sales Trend"
        chart.Export(str(chart_path))
        workbook.SaveAs(str(workbook_path), FileFormat=51)
    finally:
        if workbook is not None:
            workbook.Close(SaveChanges=True)
        if excel is not None:
            excel.Quit()
        pythoncom.CoUninitialize()


def _prefers_real_office(task: str) -> bool:
    text = str(task or "").lower()
    terms = (
        "com",
        "real excel",
        "open excel",
        "visible excel",
        "office automation",
        "\u6253\u5f00",
        "\u754c\u9762",
        "\u64cd\u7eb5",
        "\u771f\u5b9e",
        "\u81ea\u52a8\u5316",
    )
    return any(term in text for term in terms)


def _draw_chart(path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 960, 520
    margin_left, margin_top, margin_bottom = 92, 70, 80
    plot_w = width - margin_left - 50
    plot_h = height - margin_top - margin_bottom
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((margin_left, 24), "Aoryn Excel Plugin - Sales Trend", fill=(20, 34, 48), font=font)
    revenues = [int(row[1]) for row in _ROWS[1:]]
    profits = [int(row[3]) for row in _ROWS[1:]]
    max_value = max(revenues) * 1.1
    x_step = plot_w / (len(revenues) - 1)

    draw.rectangle((margin_left, margin_top, margin_left + plot_w, margin_top + plot_h), outline=(210, 210, 210))
    for i in range(5):
        y = margin_top + i * plot_h / 4
        draw.line((margin_left, y, margin_left + plot_w, y), fill=(235, 235, 235))

    def points(values: list[int]) -> list[tuple[float, float]]:
        return [
            (margin_left + idx * x_step, margin_top + plot_h - (value / max_value) * plot_h)
            for idx, value in enumerate(values)
        ]

    revenue_points = points(revenues)
    profit_points = points(profits)
    draw.line(revenue_points, fill=(37, 99, 235), width=4)
    draw.line(profit_points, fill=(22, 163, 74), width=4)
    for x, y in revenue_points:
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(37, 99, 235))
    for x, y in profit_points:
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(22, 163, 74))
    for idx, row in enumerate(_ROWS[1:]):
        x = margin_left + idx * x_step
        draw.text((x - 10, margin_top + plot_h + 18), str(row[0]), fill=(75, 85, 99), font=font)
    draw.text((margin_left + 20, height - 34), "blue: revenue   green: profit", fill=(75, 85, 99), font=font)
    image.save(path)


def _write_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(_ROWS)


def _report(*, task: str, mode: str, workbook: Path, chart: Path, csv_file: Path, com_error: str | None) -> str:
    warning = f"\n\n> Excel COM 失败后已降级为标准文件生成：{com_error}" if com_error else ""
    return (
        "# Excel 插件演示报告\n\n"
        f"## 任务\n\n{task}\n\n"
        "## 产物\n\n"
        f"- 工作簿：{workbook}\n"
        f"- 趋势图：{chart}\n"
        f"- CSV 数据：{csv_file}\n"
        f"- 执行方式：{mode}\n\n"
        "## 分析摘要\n\n"
        "- 收入从 1 月到 6 月持续增长。\n"
        "- 利润也保持上升，说明演示数据中的成本增长没有吞掉全部增量。\n"
        "- 该插件展示了软件插件可以直接生成专业应用可打开的结构化文件。\n"
        f"{warning}\n"
    )
