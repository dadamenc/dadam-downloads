#!/usr/bin/env python3
"""release의 원본 PDF마다 썸네일(.thumb.jpg)과 저화질 프리뷰(.preview.pdf)를
만들어서 같은 release에 자산으로 올리고, 전체 목록을 catalog.json에 정리한다.
원본이 아니거나(이미 .thumb.jpg / .preview.pdf) 이미 파생물이 있는 파일은 건너뛴다.

홈페이지 관리자 업로드는 Cloudflare 요청 크기 한도(100MB) 때문에
`<원본>.<업로드ID>.partNNNofMMM` 조각으로 올라온다. 조각이 다 모이면 여기서
원본으로 합치고, 첫 조각의 label(한글 표시 이름)을 원본 label로 옮긴다.
"""
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
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
PART_RE = re.compile(r"^(?P<final>.+\.pdf)\.(?P<uid>[A-Za-z0-9]+)\.part(?P<idx>\d{3})of(?P<total>\d{3})$", re.I)
STALE_PARTS_AFTER = timedelta(hours=24)


def gh(*args, cwd=None):
    result = subprocess.run(["gh", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def release_assets(tag):
    out = gh("release", "view", tag, "--repo", REPO, "--json", "assets")
    return json.loads(out)["assets"]


def delete_asset(tag, name):
    gh("release", "delete-asset", tag, name, "--repo", REPO, "--yes")


def assemble_parts(tag, tmpdir):
    assets = release_assets(tag)
    existing = {a["name"] for a in assets}
    groups = {}
    for asset in assets:
        m = PART_RE.match(asset["name"])
        if m:
            key = (m["final"], m["uid"])
            groups.setdefault(key, []).append((int(m["idx"]), int(m["total"]), asset))

    now = datetime.now(timezone.utc)
    for (final, uid), parts in groups.items():
        parts.sort(key=lambda p: p[0])
        total = parts[0][1]
        if [p[0] for p in parts] != list(range(1, total + 1)):
            oldest = min(datetime.fromisoformat(p[2]["createdAt"].replace("Z", "+00:00")) for p in parts)
            if now - oldest > STALE_PARTS_AFTER:
                print(f"[{tag}] dropping incomplete upload {final} ({uid})")
                for _, _, asset in parts:
                    delete_asset(tag, asset["name"])
            continue

        print(f"[{tag}] assembling {final} from {total} parts")
        label = (parts[0][2].get("label") or "").strip()
        out_path = tmpdir / final
        with open(out_path, "wb") as fh:
            for _, _, asset in parts:
                gh("release", "download", tag, "--repo", REPO, "--pattern", asset["name"], "--dir", str(tmpdir), "--clobber")
                part_path = tmpdir / asset["name"]
                fh.write(part_path.read_bytes())
                part_path.unlink()

        # 같은 이름으로 교체된 경우 예전 썸네일/프리뷰가 남지 않게 지운다.
        base = final[: -len(".pdf")]
        for derived in (f"{base}{THUMB_SUFFIX}", f"{base}{PREVIEW_SUFFIX}"):
            if derived in existing:
                delete_asset(tag, derived)

        spec = f"{out_path}#{label}" if label else str(out_path)
        gh("release", "upload", tag, spec, "--repo", REPO, "--clobber")
        out_path.unlink()
        for _, _, asset in parts:
            delete_asset(tag, asset["name"])


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
                "name": (asset.get("label") or "").strip() or base.replace(".", " "),
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
                assemble_parts(tag, tmpdir)
            except RuntimeError as err:
                print(f"assemble failed for {tag}: {err}", file=sys.stderr)
            try:
                catalog[key] = process_tag(tag, tmpdir)
            except RuntimeError as err:
                print(f"skip {tag}: {err}", file=sys.stderr)
                catalog[key] = []

    Path("catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(catalog, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
