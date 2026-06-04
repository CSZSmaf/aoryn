from __future__ import annotations

import html
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape

from desktop_agent.actions import Action


_OFFICE_EXE_NAMES = {
    "excel": ("EXCEL.EXE", "excel.exe"),
    "powerpoint": ("POWERPNT.EXE", "powerpnt.exe", "powerpoint.exe"),
    "word": ("WINWORD.EXE", "winword.exe"),
}

_OFFICE_CONFIG_KEYS = {
    "excel": ("excel",),
    "powerpoint": ("powerpoint", "powerpnt"),
    "word": ("word", "winword"),
}


def find_office_executable(app: str, config: Any | None = None) -> Path | None:
    app_key = str(app or "").strip().lower()
    candidates: list[str] = []
    app_launch_map = getattr(config, "app_launch_map", None)
    if isinstance(app_launch_map, dict):
        for key in _OFFICE_CONFIG_KEYS.get(app_key, (app_key,)):
            configured = str(app_launch_map.get(key) or "").strip()
            if configured:
                candidates.append(configured)

    for name in _OFFICE_EXE_NAMES.get(app_key, ()):
        found = shutil.which(name)
        if found:
            candidates.append(found)

    for root in _office_roots():
        for name in _OFFICE_EXE_NAMES.get(app_key, ()):
            candidates.append(str(root / name))

    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate).strip().strip('"')
        if not normalized or normalized.lower() in seen:
            continue
        seen.add(normalized.lower())
        resolved = shutil.which(normalized) or normalized
        path = Path(resolved)
        if path.is_file():
            return path
    return None


def office_status(app: str, *, config: Any | None = None, file_label: str = "file output") -> dict[str, Any]:
    executable = find_office_executable(app, config)
    if executable is not None:
        return {"state": "ready", "label": "Ready", "detail": str(executable)}
    return {
        "state": "available",
        "label": "File output",
        "detail": f"{app.title()} was not found, but the plugin can still generate {file_label}.",
    }


def resolve_output_dir(context: Any) -> Path:
    output_dir = getattr(context, "output_dir", None) or getattr(context, "run_dir", None) or Path.cwd()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def copy_to_run_dir(path: Path, context: Any) -> None:
    run_dir = getattr(context, "run_dir", None)
    if run_dir is None:
        return
    run_dir = Path(run_dir)
    if run_dir == path.parent:
        return
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, run_dir / path.name)
    except Exception:
        pass


def write_text_artifact(context: Any, filename: str, content: str) -> Path:
    writer = getattr(context, "write_text_file", None)
    if callable(writer):
        written = writer(filename, content)
        if written is not None:
            return Path(written)
    output_dir = resolve_output_dir(context)
    target = output_dir / filename
    target.write_text(content, encoding="utf-8")
    copy_to_run_dir(target, context)
    return target


def open_artifacts(context: Any, paths: Iterable[Path | None]) -> None:
    if not bool(getattr(context, "open_artifacts", False)):
        return
    opener = getattr(context, "open_path", None)
    if not callable(opener):
        return
    for path in paths:
        if path is None or not Path(path).exists():
            continue
        try:
            opener(Path(path))
        except Exception:
            pass


def emit(context: Any, headline: str, actions: list[Action] | None = None) -> list[Action]:
    payload = actions or [Action.from_dict({"type": "wait", "seconds": 0.2})]
    execute = getattr(context, "execute", None)
    if callable(execute):
        execute(payload, headline)
    return payload


def write_basic_xlsx(path: Path, sheet_name: str, rows: list[list[Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet_xml = _worksheet_xml(rows)
    workbook_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""
    rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return path


def write_basic_docx(path: Path, title: str, sections: list[tuple[str, list[str]]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body_parts = [_docx_paragraph(title, bold=True, size=36, color="1F4E79"), _docx_paragraph("")]
    for heading, bullets in sections:
        body_parts.append(_docx_paragraph(heading, bold=True, size=28, color="2E75B6"))
        for item in bullets:
            body_parts.append(_docx_paragraph(f"- {item}", size=22))
        body_parts.append(_docx_paragraph(""))
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{''.join(body_parts)}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body>
</w:document>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("word/document.xml", document_xml)
    return path


def write_html_deck(path: Path, title: str, slides: list[tuple[str, list[str]]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    slide_html = "\n".join(
        "<section><h1>{}</h1><ul>{}</ul></section>".format(
            html.escape(heading),
            "".join(f"<li>{html.escape(item)}</li>" for item in bullets),
        )
        for heading, bullets in slides
    )
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: "Microsoft YaHei", Segoe UI, sans-serif; background: #101820; color: #f8fafc; }}
    section {{ min-height: 100vh; box-sizing: border-box; padding: 72px 96px; border-bottom: 1px solid rgba(255,255,255,.18); }}
    h1 {{ font-size: 48px; margin: 0 0 32px; }}
    li {{ font-size: 26px; line-height: 1.55; margin: 12px 0; }}
  </style>
</head>
<body>{slide_html}</body>
</html>
""",
        encoding="utf-8",
    )
    return path


def write_basic_pptx(path: Path, title: str, slides: list[tuple[str, list[str]]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    all_slides = slides or [(title, [])]
    slide_overrides = "\n".join(
        f'  <Override PartName="/ppt/slides/slide{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for index in range(1, len(all_slides) + 1)
    )
    slide_relationships = "\n".join(
        f'  <Relationship Id="rId{index + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{index}.xml"/>'
        for index in range(1, len(all_slides) + 1)
    )
    slide_ids = "\n".join(
        f'    <p:sldId id="{255 + index}" r:id="rId{index + 1}"/>'
        for index in range(1, len(all_slides) + 1)
    )
    content_types = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
{slide_overrides}
</Types>"""
    presentation_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
  <p:sldIdLst>
{slide_ids}
  </p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000" type="screen16x9"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""
    presentation_rels = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
{slide_relationships}
</Relationships>"""
    slide_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("docProps/core.xml", _pptx_core_xml(title))
        archive.writestr("docProps/app.xml", _pptx_app_xml(len(all_slides)))
        archive.writestr("ppt/presentation.xml", presentation_xml)
        archive.writestr("ppt/_rels/presentation.xml.rels", presentation_rels)
        archive.writestr("ppt/slideMasters/slideMaster1.xml", _pptx_slide_master_xml())
        archive.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", _pptx_slide_master_rels())
        archive.writestr("ppt/slideLayouts/slideLayout1.xml", _pptx_slide_layout_xml())
        archive.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", _pptx_slide_layout_rels())
        archive.writestr("ppt/theme/theme1.xml", _pptx_theme_xml())
        for index, (heading, bullets) in enumerate(all_slides, start=1):
            archive.writestr(f"ppt/slides/slide{index}.xml", _pptx_slide_xml(heading, bullets))
            archive.writestr(f"ppt/slides/_rels/slide{index}.xml.rels", slide_rels)
    return path


def _office_roots() -> list[Path]:
    roots: list[Path] = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(env_name)
        if not base:
            continue
        roots.extend(
            [
                Path(base) / "Microsoft Office" / "root" / "Office16",
                Path(base) / "Microsoft Office" / "Office16",
                Path(base) / "Microsoft Office" / "Office15",
                Path(base) / "Programs" / "Microsoft Office" / "root" / "Office16",
                Path(base) / "Microsoft" / "WindowsApps",
            ]
        )
    return roots


def _pptx_core_xml(title: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{escape(title)}</dc:title>
  <dc:creator>Aoryn</dc:creator>
  <cp:lastModifiedBy>Aoryn</cp:lastModifiedBy>
</cp:coreProperties>"""


def _pptx_app_xml(slide_count: int) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Aoryn</Application>
  <PresentationFormat>On-screen Show (16:9)</PresentationFormat>
  <Slides>{slide_count}</Slides>
</Properties>"""


def _pptx_slide_xml(title: str, bullets: list[str]) -> str:
    bullet_xml = "".join(_pptx_text_paragraph(item, bullet=True, size=2600) for item in bullets)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      {_pptx_group_shape()}
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="Title 1"/><p:cNvSpPr/><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="685800" y="420000"/><a:ext cx="10800000" cy="900000"/></a:xfrm></p:spPr>
        <p:txBody><a:bodyPr/><a:lstStyle/>{_pptx_text_paragraph(title, size=3600, bold=True)}</p:txBody>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="3" name="Content 1"/><p:cNvSpPr/><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="950000" y="1550000"/><a:ext cx="10250000" cy="4300000"/></a:xfrm></p:spPr>
        <p:txBody><a:bodyPr/><a:lstStyle/>{bullet_xml}</p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>"""


def _pptx_text_paragraph(text: str, *, bullet: bool = False, size: int = 2400, bold: bool = False) -> str:
    bullet_xml = '<a:buChar char="•"/>' if bullet else "<a:buNone/>"
    indent = ' marL="342900" indent="-228600"' if bullet else ""
    bold_attr = ' b="1"' if bold else ""
    return (
        f"<a:p><a:pPr{indent}>{bullet_xml}</a:pPr>"
        f'<a:r><a:rPr lang="zh-CN" sz="{size}"{bold_attr}/><a:t>{escape(text)}</a:t></a:r></a:p>'
    )


def _pptx_group_shape() -> str:
    return """<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>"""


def _pptx_slide_layout_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">
  <p:cSld name="Blank"><p:spTree>{_pptx_group_shape()}</p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>"""


def _pptx_slide_layout_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>"""


def _pptx_slide_master_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree>{_pptx_group_shape()}</p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles>
</p:sldMaster>"""


def _pptx_slide_master_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>"""


def _pptx_theme_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Aoryn">
  <a:themeElements>
    <a:clrScheme name="Aoryn">
      <a:dk1><a:srgbClr val="111827"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="374151"/></a:dk2><a:lt2><a:srgbClr val="F8FAFC"/></a:lt2>
      <a:accent1><a:srgbClr val="2563EB"/></a:accent1><a:accent2><a:srgbClr val="16A34A"/></a:accent2>
      <a:accent3><a:srgbClr val="F59E0B"/></a:accent3><a:accent4><a:srgbClr val="DC2626"/></a:accent4>
      <a:accent5><a:srgbClr val="7C3AED"/></a:accent5><a:accent6><a:srgbClr val="0891B2"/></a:accent6>
      <a:hlink><a:srgbClr val="2563EB"/></a:hlink><a:folHlink><a:srgbClr val="7C3AED"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="Aoryn"><a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/></a:minorFont></a:fontScheme>
    <a:fmtScheme name="Aoryn"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme>
  </a:themeElements>
</a:theme>"""


def _worksheet_xml(rows: list[list[Any]]) -> str:
    row_xml: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells: list[str] = []
        for col_index, value in enumerate(row, start=1):
            ref = f"{_excel_col(col_index)}{row_index}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_xml)}</sheetData></worksheet>'
    )


def _excel_col(index: int) -> str:
    label = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        label = chr(65 + remainder) + label
    return label


def _docx_paragraph(text: str, *, bold: bool = False, size: int | None = None, color: str | None = None) -> str:
    props: list[str] = []
    if bold:
        props.append("<w:b/>")
    if size is not None:
        props.append(f'<w:sz w:val="{int(size)}"/>')
    if color:
        props.append(f'<w:color w:val="{escape(color)}"/>')
    rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
    return f"<w:p><w:r>{rpr}<w:t>{escape(text)}</w:t></w:r></w:p>"
