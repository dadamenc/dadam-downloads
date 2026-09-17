#!/usr/bin/env python3
"""release의 원본 PDF마다 썸네일(.thumb.jpg)과 저화질 프리뷰(.preview.pdf)를
만들어서 같은 release에 자산으로 올리고, 전체 목록을 catalog.json에 정리한다.
원본이 아니거나(이미 .thumb.jpg / .preview.pdf) 이미 파생물이 있는 파일은 건너뛴다.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz  # PyMuPDF

REPO = "dadamenc/dadam-downloads"
TAGS = {
    "catalog-v1": "catalog",
    "test-reports-v1": "test-reports",
}
THUMB_SUFFIX = ".thumb.jpg"
PREVIEW_SUFFIX = ".preview.pdf"
THUMB_WIDTH = 520
THUMB_QUALITY = 72
PREVIEW_ZOOM = 100 / 72  # ~100 DPI
PREVIEW_QUALITY = 55


def gh(*args, cwd=None):
    result = subprocess.run(["gh", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def release_assets(tag):
    out = gh("release", "view", tag, "--repo", REPO, "--json", "assets")
    return json.loads(out)["assets"]


def is_original(name):
    lower = name.lower()
    return lower.endswith(".pdf") and not lower.endswith(THUMB_SUFFIX.lower()) and not lower.endswith(
        PREVIEW_SUFFIX.lower()
    )


def make_thumb(src_path, out_path):
    doc = fitz.open(src_path)
    page = doc[0]
    zoom = THUMB_WIDTH / page.rect.width
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    pix.save(str(out_path), jpg_quality=THUMB_QUALITY)
    doc.close()


def make_preview(src_path, out_path):
    src = fitz.open(src_path)
    out = fitz.open()
    mat = fitz.Matrix(PREVIEW_ZOOM, PREVIEW_ZOOM)
    for page in src:
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("jpeg", jpg_quality=PREVIEW_QUALITY)
        rect = fitz.Rect(0, 0, pix.width, pix.height)
        newpage = out.new_page(width=pix.width, height=pix.height)
        newpage.insert_image(rect, stream=img_bytes)
    out.save(str(out_path), garbage=4, deflate=True)
    out.close()
    src.close()


def process_tag(tag, tmpdir):
    assets = release_assets(tag)
    names = {a["name"] for a in assets}
    originals = [a for a in assets if is_original(a["name"])]

    entries = []
    for asset in originals:
        base = asset["name"][: -len(".pdf")]
        thumb_name = f"{base}{THUMB_SUFFIX}"
        preview_name = f"{base}{PREVIEW_SUFFIX}"
        needs_thumb = thumb_name not in names
        needs_preview = preview_name not in names

        if needs_thumb or needs_preview:
            print(f"[{tag}] generating derivatives for {asset['name']}")
            local_pdf = tmpdir / asset["name"]
            gh(
                "release",
                "download",
                tag,
                "--repo",
                REPO,
                "--pattern",
                asset["name"],
                "--dir",
                str(tmpdir),
                "--clobber",
            )
            if needs_thumb:
                thumb_path = tmpdir / thumb_name
                make_thumb(local_pdf, thumb_path)
                gh("release", "upload", tag, str(thumb_path), "--repo", REPO, "--clobber")
                names.add(thumb_name)
            if needs_preview:
                preview_path = tmpdir / preview_name
                make_preview(local_pdf, preview_path)
                gh("release", "upload", tag, str(preview_path), "--repo", REPO, "--clobber")
                names.add(preview_name)
            local_pdf.unlink(missing_ok=True)

        entries.append(
            {
                "name": base.replace(".", " "),
                "file": asset["name"],
                "thumb": thumb_name if thumb_name in names else None,
                "preview": preview_name if preview_name in names else None,
            }
        )

    entries.sort(key=lambda e: e["name"])
    return entries


def main():
    catalog = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for tag, key in TAGS.items():
            try:
                catalog[key] = process_tag(tag, tmpdir)
            except RuntimeError as err:
                print(f"skip {tag}: {err}", file=sys.stderr)
                catalog[key] = []

    Path("catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(catalog, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
