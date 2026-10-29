"""Joriy papka yoki faylning «ekrani»: rasm ko'rinishida.

  • Papka   → Explorer'ga o'xshash ro'yxat (nomi, sanasi, hajmi).
  • Rasm    → rasmning o'zi.
  • PDF     → 1-sahifa.
  • HTML    → brauzerda ochilgandagi ko'rinishi.
  • Word/Excel/PowerPoint → 1-sahifa (MS Office yoki LibreOffice orqali PDF ga o'girib).
  • CorelDRAW / Illustrator → fayl ichidagi eskiz / 1-sahifa.
  • Matn/kod → birinchi qatorlari.
  • Boshqalar → fayl haqida kartochka.

Rasm Windows'dagi Edge (yoki Chrome) brauzerida yashirin chiziladi - ekranda hech narsa ochilmaydi.
Qo'shimcha kutubxona shart emas. Pillow / PyMuPDF o'rnatilgan bo'lsa, rasm va PDF tezroq chiqadi.
"""
import base64
import html
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image
except Exception:  # noqa: BLE001
    Image = None
try:
    import pymupdf as fitz
except Exception:  # noqa: BLE001
    try:
        import fitz  # type: ignore
    except Exception:  # noqa: BLE001
        fitz = None

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".ico", ".psd"}
BROWSER_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".ico", ".svg"}
TEXT_EXT = {".txt", ".csv", ".log", ".md", ".json", ".xml", ".ini", ".cfg", ".env", ".py", ".js",
            ".css", ".php", ".sql", ".bat", ".ps1", ".yml", ".yaml"}
HTML_EXT = {".html", ".htm"}
OFFICE_EXT = {".doc", ".docx", ".rtf", ".odt", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp"}
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # yordamchi dasturlar oynasiz ishlasin

EXT_COLORS = {".pdf": "#dc3c32", ".doc": "#285ac8", ".docx": "#285ac8", ".xls": "#1e8c46",
              ".xlsx": "#1e8c46", ".csv": "#1e8c46", ".ppt": "#d25a28", ".pptx": "#d25a28",
              ".jpg": "#9650c8", ".jpeg": "#9650c8", ".png": "#9650c8", ".tif": "#9650c8",
              ".tiff": "#9650c8", ".psd": "#2878c8", ".cdr": "#3ca03c", ".ai": "#e68c1e",
              ".zip": "#786450", ".rar": "#786450", ".html": "#e66e28", ".exe": "#5a5a6e"}


class PreviewError(Exception):
    pass


# ─────────────────────────── Brauzer orqali rasmga olish ───────────────────────────

def _find_browser() -> str | None:
    cands = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for c in cands:
        if os.path.isfile(c):
            return c
    return shutil.which("msedge") or shutil.which("chrome") or shutil.which("chromium")


def _shot(uri: str, width: int = 1366, height: int = 900) -> bytes | None:
    exe = _find_browser()
    if not exe:
        raise PreviewError("Kompyuterda Edge yoki Chrome topilmadi")
    with tempfile.TemporaryDirectory(prefix="filebot_", ignore_cleanup_errors=True) as tmp:
        out = Path(tmp) / "shot.png"
        args = [exe, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                "--no-first-run", "--no-default-browser-check", "--disable-extensions",
                "--allow-file-access-from-files", f"--window-size={width},{height}",
                "--virtual-time-budget=4000", f"--screenshot={out}", uri]
        if sys.platform == "win32":  # ochiq turgan Edge/Chrome profiliga tegmaslik uchun
            args.insert(1, f"--user-data-dir={Path(tmp) / 'profile'}")
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=NO_WINDOW)
        # Ba'zi brauzer versiyalari rasmni saqlab bo'lgach ham yopilmaydi - fayl paydo bo'lishini kutamiz
        last, deadline = -1, time.monotonic() + 45
        try:
            while time.monotonic() < deadline:
                if out.exists():
                    size = out.stat().st_size
                    if size > 0 and size == last:
                        return out.read_bytes()
                    last = size
                elif proc.poll() is not None:
                    return out.read_bytes() if out.exists() else None
                time.sleep(0.4)
            return None
        finally:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except Exception:  # noqa: BLE001
                    pass


def _html_shot(body: str, width: int, height: int) -> bytes:
    page = f"""<!doctype html><html><head><meta charset="utf-8"><style>
    *{{box-sizing:border-box}} body{{margin:0;background:#fff;color:#20242c;
    font:15px "Segoe UI","Segoe UI Emoji",Arial,sans-serif}}
    .head{{background:#f3f6fa;padding:20px 28px 16px;border-bottom:1px solid #e2e7ee}}
    .title{{font-size:24px;font-weight:700;display:flex;align-items:center;gap:12px}}
    .sub{{color:#6e7682;margin-top:6px;display:flex;justify-content:space-between;gap:20px}}
    .sub span:first-child{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    table{{width:100%;border-collapse:collapse}} th{{text-align:left;color:#6e7682;font-weight:400;
    padding:10px 12px;border-bottom:1px solid #e2e7ee}} td{{padding:7px 12px;white-space:nowrap}}
    tr:nth-child(even) td{{background:#fafbfd}} .name{{max-width:620px;overflow:hidden;text-overflow:ellipsis}}
    .dir{{font-weight:700}} .muted{{color:#6e7682}} .r{{text-align:right}}
    .ico{{display:inline-block;width:26px;text-align:center;margin-right:8px;font-size:18px}}
    .badge{{display:inline-block;min-width:34px;padding:1px 4px;margin-right:8px;border-radius:3px;
    color:#fff;font-size:10px;font-weight:700;text-align:center;vertical-align:middle}}
    .more{{color:#286edc;padding:12px 28px}}
    </style></head><body>{body}</body></html>"""
    with tempfile.TemporaryDirectory(prefix="filebot_", ignore_cleanup_errors=True) as tmp:
        f = Path(tmp) / "view.html"
        f.write_text(page, encoding="utf-8")
        png = _shot(f.as_uri(), width, height)
    if not png:
        raise PreviewError("Brauzer rasmni chiza olmadi")
    return png


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def _mtime(p: Path) -> str:
    try:
        return datetime.fromtimestamp(p.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
    except OSError:
        return ""


def _badge(ext: str) -> str:
    label = html.escape(ext[1:5].upper()) if ext else "—"
    return f'<span class="badge" style="background:{EXT_COLORS.get(ext, "#78808c")}">{label}</span>'


# ─────────────────────────── Papka ───────────────────────────

def render_folder(path: Path, dirs: list[Path], files: list[tuple[Path, int]],
                  max_rows: int = 45) -> bytes:
    entries: list[tuple[Path, int | None]] = [(p, None) for p in dirs] + list(files)
    shown = entries[:max_rows]
    rows = []
    for p, size in shown:
        if size is None:
            name = f'<span class="ico">📁</span><span class="dir">{html.escape(p.name)}</span>'
        else:
            name = f'{_badge(p.suffix.lower())}{html.escape(p.name)}'
        rows.append(f'<tr><td class="name">{name}</td><td class="muted">{_mtime(p)}</td>'
                    f'<td class="muted r">{"" if size is None else _size(size)}</td></tr>')
    if not rows:
        rows.append('<tr><td class="muted" colspan="3">Papka bo\'sh</td></tr>')
    more = (f'<div class="more">… yana {len(entries) - max_rows} ta (botdagi sahifalarda)</div>'
            if len(entries) > max_rows else "")
    body = (f'<div class="head"><div class="title"><span>📂</span>{html.escape(path.name or str(path))}</div>'
            f'<div class="sub"><span>{html.escape(str(path))}</span>'
            f'<span>{len(dirs)} papka · {len(files)} fayl</span></div></div>'
            f'<table><tr><th>Nomi</th><th>O\'zgartirilgan</th><th class="r">Hajmi</th></tr>'
            f'{"".join(rows)}</table>{more}')
    height = 120 + 36 * max(len(shown), 1) + (60 if more else 20)
    return _html_shot(body, 1100, min(height, 4000))


# ─────────────────────────── Fayllar ───────────────────────────

def render_file(path: Path) -> tuple[bytes, str]:
    """(rasm baytlari, izoh). Ko'rinish chiqmasa, fayl haqida kartochka qaytaradi."""
    ext = path.suffix.lower()
    note = "Bu turdagi fayl uchun ko'rinish yo'q. Faylni yuklab oling."
    try:
        if ext in IMAGE_EXT:
            res = _image(path)
            if res:
                return res, "rasm"
        elif ext == ".pdf":
            res = _pdf(path)
            if res:
                return res
        elif ext == ".ai":  # Illustrator fayllari odatda PDF bilan mos saqlanadi
            res = _pdf(path, "Illustrator · ")
            if res:
                return res
        elif ext in (".cdr", ".cdt"):
            thumb = _zip_thumbnail(path) if zipfile.is_zipfile(path) else None
            if thumb:
                return thumb, "CorelDRAW eskizi"
        elif ext in HTML_EXT or ext == ".svg":
            shot = _shot(path.resolve().as_uri())
            if shot:
                return shot, "brauzerdagi ko'rinishi"
        elif ext in OFFICE_EXT:
            res = _office(path)
            if res:
                return res
            note = "Word/Excel ko'rinishi uchun kompyuterda MS Office yoki LibreOffice kerak."
        elif ext in TEXT_EXT:
            return _text(path), "matn"
    except Exception as e:  # noqa: BLE001 - har qanday xatoda kartochka ko'rsatamiz
        note = f"Ko'rinishni olib bo'lmadi: {e}"
    return _card(path, note), "ma'lumot"


def _image(path: Path) -> bytes | None:
    ext = path.suffix.lower()
    if Image is not None:
        try:
            import io
            with Image.open(path) as im:
                im.seek(0)
                im = im.convert("RGBA")
                im.thumbnail((2400, 2400))
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                buf = io.BytesIO()
                bg.save(buf, "JPEG", quality=88)
                return buf.getvalue()
        except Exception:  # noqa: BLE001
            pass
    if ext in (".jpg", ".jpeg", ".png") and path.stat().st_size < 9_000_000:
        return path.read_bytes()  # Telegram o'zi ko'rsata oladi
    if ext in BROWSER_IMAGE_EXT:
        uri = path.resolve().as_uri()
        return _html_shot(f'<img src="{uri}" style="max-width:1366px;max-height:1000px;display:block;margin:auto">',
                          1366, 1000)
    return None


def _pdf(path: Path, label: str = "") -> tuple[bytes, str] | None:
    if fitz is not None:
        with fitz.open(str(path)) as doc:
            page = doc[0]
            zoom = min(2.0, 1600 / max(page.rect.width, 1))
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            return pix.tobytes("png"), f"{label}1-sahifa / {doc.page_count}"
    # PyMuPDF yo'q - Windows'ning o'zidagi PDF chizuvchisi (Windows 10/11 da bor)
    if sys.platform == "win32":
        res = _pdf_windows(path)
        if res:
            png, pages = res
            return png, f"{label}1-sahifa / {pages}" if pages else f"{label}1-sahifa"
    return None


WINRT_PDF_PS = r"""
param([string]$src, [string]$outDir)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$ext = [System.WindowsRuntimeSystemExtensions].GetMethods()
$asTaskOp = $ext | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
$asTaskAct = $ext | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' } | Select-Object -First 1
function Await($op, [Type]$t) { $task = $asTaskOp.MakeGenericMethod($t).Invoke($null, @($op)); $null = $task.Wait(-1); $task.Result }
function AwaitAction($op) { $task = $asTaskAct.Invoke($null, @($op)); $null = $task.Wait(-1) }
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Storage.StorageFolder, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($src)) ([Windows.Storage.StorageFile])
$doc = Await ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])
$page = $doc.GetPage(0)
$folder = Await ([Windows.Storage.StorageFolder]::GetFolderFromPathAsync($outDir)) ([Windows.Storage.StorageFolder])
$out = Await ($folder.CreateFileAsync('page.png', [Windows.Storage.CreationCollisionOption]::ReplaceExisting)) ([Windows.Storage.StorageFile])
$stream = Await ($out.OpenAsync([Windows.Storage.FileAccessMode]::ReadWrite)) ([Windows.Storage.Streams.IRandomAccessStream])
$opt = New-Object Windows.Data.Pdf.PdfPageRenderOptions
$opt.DestinationWidth = [uint32][Math]::Min(1600, [Math]::Max(800, $page.Size.Width * 2))
AwaitAction ($page.RenderToStreamAsync($stream, $opt))
$stream.Dispose(); $page.Dispose()
Write-Output $doc.PageCount
"""


def _pdf_windows(path: Path) -> tuple[bytes, int] | None:
    with tempfile.TemporaryDirectory(prefix="filebot_", ignore_cleanup_errors=True) as tmp:
        script = Path(tmp) / "pdf.ps1"
        script.write_text(WINRT_PDF_PS, encoding="utf-8-sig")
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-File", str(script), str(path.resolve()), tmp],
                           timeout=60, capture_output=True, creationflags=NO_WINDOW)
        png = Path(tmp) / "page.png"
        if not png.exists() or png.stat().st_size == 0:
            return None
        out = (r.stdout or b"").decode(errors="ignore").strip().splitlines()
        pages = int(out[-1]) if out and out[-1].strip().isdigit() else 0
        return png.read_bytes(), pages


def _zip_thumbnail(path: Path) -> bytes | None:
    """CorelDRAW X4+ fayli ichida tayyor eskiz (previews/thumbnail.png) bo'ladi."""
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith((".png", ".bmp", ".jpg"))
                 and ("preview" in n.lower() or "thumbnail" in n.lower())]
        if not names:
            return None
        data = z.read(max(names, key=lambda n: z.getinfo(n).file_size))
    mime = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
    b64 = base64.b64encode(data).decode()
    return _html_shot(f'<div style="padding:20px;text-align:center"><img src="data:{mime};base64,{b64}" '
                      f'style="width:600px;image-rendering:auto;border:1px solid #e2e7ee"></div>', 660, 520)


def _office(path: Path) -> tuple[bytes, str] | None:
    with tempfile.TemporaryDirectory(prefix="filebot_", ignore_cleanup_errors=True) as tmp:
        pdf = Path(tmp) / (path.stem + ".pdf")
        soffice = (shutil.which("soffice") or
                   next((p for p in [os.path.expandvars(r"%ProgramFiles%\LibreOffice\program\soffice.exe"),
                                     os.path.expandvars(r"%ProgramFiles(x86)%\LibreOffice\program\soffice.exe")]
                         if os.path.isfile(p)), None))
        if soffice:
            subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(path)],
                           timeout=120, capture_output=True, creationflags=NO_WINDOW)
        if not pdf.exists() and sys.platform == "win32":
            _ms_office_to_pdf(path, pdf)
        if pdf.exists():
            return _pdf(pdf)
    return None


def _ms_office_to_pdf(src: Path, out: Path) -> None:
    """Kompyuterda MS Office bo'lsa - u orqali PDF ga o'giramiz (oynasiz, faqat o'qish uchun)."""
    ext = src.suffix.lower()
    s, o = str(src).replace("'", "''"), str(out).replace("'", "''")
    if ext in (".doc", ".docx", ".rtf", ".odt"):
        ps = (f"$a=New-Object -ComObject Word.Application;$a.Visible=$false;$a.DisplayAlerts=0;"
              f"try{{$d=$a.Documents.Open('{s}',$false,$true);$d.ExportAsFixedFormat('{o}',17);"
              f"$d.Close($false)}}finally{{$a.Quit()}}")
    elif ext in (".xls", ".xlsx", ".ods"):
        ps = (f"$a=New-Object -ComObject Excel.Application;$a.Visible=$false;$a.DisplayAlerts=$false;"
              f"try{{$b=$a.Workbooks.Open('{s}',0,$true);$b.ActiveSheet.ExportAsFixedFormat(0,'{o}');"
              f"$b.Close($false)}}finally{{$a.Quit()}}")
    else:
        ps = (f"$a=New-Object -ComObject PowerPoint.Application;"
              f"try{{$p=$a.Presentations.Open('{s}',$true,$false,$false);$p.SaveAs('{o}',32);"
              f"$p.Close()}}finally{{$a.Quit()}}")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                   timeout=120, capture_output=True, creationflags=NO_WINDOW)


def _text(path: Path, max_lines: int = 60) -> bytes:
    raw = path.read_bytes()[:20000]
    text = ""
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    lines = text.replace("\t", "    ").splitlines()[:max_lines]
    numbered = "\n".join(f'<span style="color:#6e7480">{i + 1:>3}</span>  {html.escape(l)}'
                         for i, l in enumerate(lines))
    body = (f'<div style="background:#1e2026;color:#dce0e8;min-height:100vh;padding:18px 20px">'
            f'<div style="font:700 18px Segoe UI,Arial;margin-bottom:12px">{html.escape(path.name)}</div>'
            f'<pre style="margin:0;font:14px/22px Consolas,monospace;white-space:pre;overflow:hidden">'
            f'{numbered}</pre></div>')
    return _html_shot(body, 1200, 80 + 22 * max(len(lines), 1))


def _card(path: Path, note: str) -> bytes:
    st = path.stat()
    ext = path.suffix.lower()
    color = EXT_COLORS.get(ext, "#78808c")
    body = (f'<div style="display:flex;gap:36px;padding:44px">'
            f'<div style="position:relative;width:100px;height:130px;border:2px solid #aab0ba;flex:none">'
            f'<div style="position:absolute;left:-12px;right:-12px;top:60px;padding:8px 0;background:{color};'
            f'color:#fff;font:700 22px Segoe UI,Arial;text-align:center">{html.escape(ext[1:6].upper() or "FAYL")}</div></div>'
            f'<div style="min-width:0"><div style="font-size:26px;font-weight:700;overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap;max-width:640px">{html.escape(path.name)}</div>'
            f'<div class="muted" style="margin-top:14px;line-height:28px;font-size:17px">'
            f'Hajmi: {_size(st.st_size)}<br>O\'zgartirilgan: {_mtime(path)}<br>'
            f'<span style="display:inline-block;max-width:640px;overflow:hidden;text-overflow:ellipsis;'
            f'white-space:nowrap">Joyi: {html.escape(str(path.parent))}</span></div>'
            f'<div style="color:#286edc;margin-top:16px">{html.escape(note)}</div></div></div>')
    return _html_shot(body, 900, 260)
