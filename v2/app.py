"""
Backend web para comparar las implementaciones de cifrado/descifrado en C, Java y C#.
Usa las versiones mantenidas en ../c, ../java y ../cs.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import math
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from uuid import uuid4

from flask import Flask, abort, jsonify, render_template, request, send_file, session
from flask_cors import CORS
from PIL import Image

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(32).hex())
CORS(app)

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
C_DIR = ROOT_DIR / "c"
JAVA_DIR = ROOT_DIR / "java"
CS_DIR = ROOT_DIR / "cs"
BUILD_DIR = BASE_DIR / "build"
TEMP_ROOT = Path(tempfile.gettempdir()) / "tt_v2_runtime"
SESSIONS_ROOT = TEMP_ROOT / "sessions"

C_CIFRADOR = BUILD_DIR / "cifrador_c"
C_DESCIFRADOR = BUILD_DIR / "descifrador_c"
C_COMPLETO = BUILD_DIR / "completo_c"
JAVA_BUILD_DIR = BUILD_DIR / "java"
CS_CIFRADO_PROJ = BUILD_DIR / "cs" / "Cifrado" / "Cifrado.csproj"
CS_DESCIFRADO_PROJ = BUILD_DIR / "cs" / "Descifrado" / "Descifrado.csproj"
CS_COMPLETO_PROJ = BUILD_DIR / "cs" / "Completo" / "Completo.csproj"
CS_CIFRADO_DLL = BUILD_DIR / "cs" / "Cifrado" / "bin" / "Release" / "net10.0" / "Cifrado.dll"
CS_DESCIFRADO_DLL = BUILD_DIR / "cs" / "Descifrado" / "bin" / "Release" / "net10.0" / "Descifrado.dll"
CS_COMPLETO_DLL = BUILD_DIR / "cs" / "Completo" / "bin" / "Release" / "net10.0" / "Completo.dll"
ALLOWED_IMAGE_EXTENSIONS = {".png", ".bmp", ".tif", ".tiff"}
EXPORT_FORMATS = {
    "png": ("PNG", ".png", "image/png"),
    "jpg": ("JPEG", ".jpg", "image/jpeg"),
    "jpeg": ("JPEG", ".jpeg", "image/jpeg"),
    "bmp": ("BMP", ".bmp", "image/bmp"),
    "tiff": ("TIFF", ".tiff", "image/tiff"),
    "webp": ("WEBP", ".webp", "image/webp"),
}


def tool_exists(name: str) -> bool:
    return shutil.which(name) is not None


def allowed_image_filename(filename: str | None) -> bool:
    if not filename:
        return False
    return Path(filename).suffix.lower() in ALLOWED_IMAGE_EXTENSIONS


def run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def img_to_b64(path: Path) -> str | None:
    try:
        img = Image.open(path).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_rgb_pixels(path: Path) -> str:
    with Image.open(path) as img:
        rgb = img.convert("RGB")
        return hashlib.sha256(rgb.tobytes()).hexdigest()


def describe_png(path: Path) -> dict[str, int | str]:
    with Image.open(path) as img:
        width, height = img.size
        channels = len(img.getbands())
    return {
        "width": width,
        "height": height,
        "channels": channels,
        "png_size_bytes": path.stat().st_size,
        "sha256_png": sha256_file(path),
        "sha256_rgb": sha256_rgb_pixels(path),
    }


def unique_name(prefix: str, suffix: str) -> str:
    return f"{prefix}_{uuid4().hex}{suffix}"


def sanitize_output_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name.strip())
    return cleaned.strip("._") or "imagen_descifrada"


def ensure_runtime_dirs() -> None:
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)


def get_session_id() -> str:
    sid = session.get("client_session_id")
    if not sid:
        sid = uuid4().hex
        session["client_session_id"] = sid
    return sid


def session_root(session_id: str) -> Path:
    return SESSIONS_ROOT / session_id


def session_runtime_root(session_id: str) -> Path:
    return session_root(session_id) / "runtime"


def session_download_root(session_id: str) -> Path:
    return session_root(session_id) / "downloads"


def ensure_session_dirs(session_id: str) -> None:
    ensure_runtime_dirs()
    session_runtime_root(session_id).mkdir(parents=True, exist_ok=True)
    session_download_root(session_id).mkdir(parents=True, exist_ok=True)


def clear_session_artifacts(session_id: str) -> None:
    safe_rmtree(session_root(session_id))
    ensure_session_dirs(session_id)


def make_runtime_dir(session_id: str, prefix: str) -> Path:
    ensure_session_dirs(session_id)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=session_runtime_root(session_id)))


def make_temp_png(session_id: str) -> Path:
    ensure_session_dirs(session_id)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False, dir=session_runtime_root(session_id)) as tmp:
        return Path(tmp.name)


def safe_rmtree(path: Path | None) -> None:
    if not path:
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def strip_internal_paths(result: dict) -> dict:
    cleaned = dict(result)
    for key in ("session_file", "cipher_path", "prev_path", "preview_path", "workdir"):
        cleaned.pop(key, None)
    return cleaned


def parse_session_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value
    return data


def rewrite_session_file(path: Path, entries: dict[str, str], remove_keys: set[str] | None = None) -> None:
    if not path.exists():
        return
    data = parse_session_file(path)
    for key in remove_keys or set():
        data.pop(key, None)
    for key, value in entries.items():
        if value:
            data[key] = value

    lines = ["# Sesion de cifrado"]
    preferred_order = [
        "ancho",
        "alto",
        "canales",
        "rondas",
        "original_format",
        "z_hex",
        "salt_hex",
    ]
    used = set()
    for key in preferred_order:
        if key in data:
            lines.append(f"{key}={data[key]}")
            used.add(key)
    for key in sorted(k for k in data.keys() if k not in used):
        lines.append(f"{key}={data[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def rewrite_session_files_in_workdir(workdir: Path, original_format: str) -> None:
    if not workdir.exists():
        return
    for session_path in workdir.glob("*.session.txt"):
        rewrite_session_file(
            session_path,
            {"original_format": original_format},
            remove_keys={"x_prev_path", "x_cur_path"},
        )


def collect_bundle_artifacts(result: dict) -> list[Path]:
    files: list[Path] = []
    for key in ("cipher_path", "prev_path", "session_file"):
        value = result.get(key)
        if not value:
            continue
        path = Path(value)
        if path.exists() and path.is_file():
            files.append(path)
    return files


def classify_bundle_artifact_name(name: str) -> str | None:
    lower = name.lower()
    if lower.endswith(".session.txt"):
        return "session"
    if lower.endswith(".prev.bin"):
        return "prev"
    if lower.endswith(".bin"):
        return "cipher"
    return None


def extract_bundle_artifacts(bundle_file, tmpdir: Path) -> dict[str, dict[str, Path]]:
    extracted: dict[str, dict[str, Path]] = {}
    duplicates: list[str] = []
    bundle_stream = getattr(bundle_file, "stream", bundle_file)
    with zipfile.ZipFile(bundle_stream) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            rel = Path(info.filename)
            if len(rel.parts) < 2:
                continue
            folder = rel.parts[0]
            kind = classify_bundle_artifact_name(rel.name)
            if not kind:
                continue
            lang_bucket = extracted.setdefault(folder, {})
            if kind in lang_bucket:
                duplicates.append(f"{folder}:{kind}")
                continue
            target_dir = tmpdir / folder
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / rel.name
            with zf.open(info, "r") as src, target_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            lang_bucket[kind] = target_path
    if duplicates:
        raise ValueError("El paquete .zip contiene múltiples archivos candidatos para el mismo artefacto.")
    return extracted


def build_session_from_artifacts(session_path: Path, cipher_path: Path, prev_path: Path) -> tuple[dict[str, str], str, str]:
    session_data = parse_session_file(session_path)
    session_data["x_cur_path"] = str(cipher_path)
    session_data["x_prev_path"] = str(prev_path)
    original_format = session_data.get("original_format", "png").lower()
    if original_format not in EXPORT_FORMATS:
        original_format = "png"
    output_suffix = EXPORT_FORMATS[original_format][1]
    return session_data, original_format, output_suffix


def new_shared_session() -> dict[str, str]:
    return {
        "z_hex": os.urandom(32).hex(),
        "salt_hex": os.urandom(32).hex(),
    }


def compute_histogram(image_path: Path) -> dict[str, list[int]]:
    img = Image.open(image_path).convert("RGB")
    data = img.tobytes()
    hist = {
        "r": [0] * 256,
        "g": [0] * 256,
        "b": [0] * 256,
    }
    for i in range(0, len(data), 3):
        hist["r"][data[i]] += 1
        hist["g"][data[i + 1]] += 1
        hist["b"][data[i + 2]] += 1
    return hist


def compute_metrics(image_path: Path) -> list[dict[str, float | int]]:
    img = Image.open(image_path).convert("RGB")
    data = list(img.tobytes())
    n = len(data)
    if n == 0:
        return []

    hist = [0] * 256
    for value in data:
        hist[value] += 1

    entropy = 0.0
    for count in hist:
        if count:
            p = count / n
            entropy -= p * math.log2(p)

    expected = n / 256.0
    chi = sum(((count - expected) ** 2) / expected for count in hist)

    pair_count = 0
    sum_x = 0.0
    sum_y = 0.0
    sum_x2 = 0.0
    sum_y2 = 0.0
    sum_xy = 0.0
    width, height = img.size
    raw = img.tobytes()
    for y in range(height):
        for x in range(width - 1):
            left_base = (y * width + x) * 3
            right_base = left_base + 3
            for c in range(3):
                vx = float(raw[left_base + c])
                vy = float(raw[right_base + c])
                pair_count += 1
                sum_x += vx
                sum_y += vy
                sum_x2 += vx * vx
                sum_y2 += vy * vy
                sum_xy += vx * vy

    if pair_count == 0:
        corr = 0.0
    else:
        mean_x = sum_x / pair_count
        mean_y = sum_y / pair_count
        cov = (sum_xy / pair_count) - (mean_x * mean_y)
        var_x = (sum_x2 / pair_count) - (mean_x * mean_x)
        var_y = (sum_y2 / pair_count) - (mean_y * mean_y)
        denom = math.sqrt(max(var_x, 0.0) * max(var_y, 0.0))
        corr = cov / denom if denom > 0.0 else 0.0

    return [{
        "gen": 1,
        "entropy": entropy,
        "chi": chi,
        "corr": corr,
    }]


def compare_recovery(original_path: Path, recovered_path: Path) -> str:
    try:
        a = Image.open(original_path).convert("RGB")
        b = Image.open(recovered_path).convert("RGB")
    except Exception:
        return "ERROR"

    if a.size != b.size:
        return "ERROR"
    return "OK" if a.tobytes() == b.tobytes() else "FAIL"


def ensure_c_binaries() -> tuple[bool, str]:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    if not tool_exists("gcc"):
        return False, "gcc no está instalado."

    sources = [
        C_DIR / "cifrado.c",
        C_DIR / "descifrado.c",
        C_DIR / "automata.c",
        C_DIR / "permutaciones.c",
        C_DIR / "llaves.c",
        C_DIR / "automata.h",
        C_DIR / "permutaciones.h",
        C_DIR / "llaves.h",
    ]
    newest = max(src.stat().st_mtime for src in sources if src.exists())

    def needs_build(output: Path) -> bool:
        return (not output.exists()) or output.stat().st_mtime < newest

    if needs_build(C_CIFRADOR):
        proc = run_cmd([
            "gcc", "-std=c11", "-O2",
            str(C_DIR / "cifrado.c"),
            str(C_DIR / "automata.c"),
            str(C_DIR / "permutaciones.c"),
            str(C_DIR / "llaves.c"),
            "-I", str(C_DIR),
            "-lcrypto",
            "-o", str(C_CIFRADOR),
        ], cwd=ROOT_DIR)
        if proc.returncode != 0:
            return False, proc.stderr[:400]

    if needs_build(C_DESCIFRADOR):
        proc = run_cmd([
            "gcc", "-std=c11", "-O2",
            str(C_DIR / "descifrado.c"),
            str(C_DIR / "automata.c"),
            str(C_DIR / "permutaciones.c"),
            str(C_DIR / "llaves.c"),
            "-I", str(C_DIR),
            "-lcrypto",
            "-o", str(C_DESCIFRADOR),
        ], cwd=ROOT_DIR)
        if proc.returncode != 0:
            return False, proc.stderr[:400]

    if needs_build(C_COMPLETO):
        proc = run_cmd([
            "gcc", "-std=c11", "-O2",
            str(C_DIR / "completo.c"),
            str(C_DIR / "automata.c"),
            str(C_DIR / "permutaciones.c"),
            str(C_DIR / "llaves.c"),
            "-I", str(C_DIR),
            "-lcrypto",
            "-o", str(C_COMPLETO),
        ], cwd=ROOT_DIR)
        if proc.returncode != 0:
            return False, proc.stderr[:400]

    return True, ""


def ensure_java_build() -> tuple[bool, str]:
    if not tool_exists("javac") or not tool_exists("java"):
        return False, "javac/java no están instalados."
    JAVA_BUILD_DIR.mkdir(parents=True, exist_ok=True)
    sources = sorted(str(p) for p in JAVA_DIR.glob("*.java"))
    if not sources:
        return False, "No se encontraron fuentes Java."

    newest = max(Path(src).stat().st_mtime for src in sources)
    marker = JAVA_BUILD_DIR / "Cifrado.class"
    if marker.exists() and marker.stat().st_mtime >= newest:
        return True, ""

    proc = run_cmd(["javac", "-d", str(JAVA_BUILD_DIR), *sources], cwd=ROOT_DIR, timeout=240)
    if proc.returncode != 0:
        return False, proc.stderr[:400]
    return True, ""


def write_csproj(path: Path, startup_object: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net10.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
    <StartupObject>{startup_object}</StartupObject>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="../../../../cs/*.cs" />
  </ItemGroup>
  <ItemGroup>
    <PackageReference Include="BouncyCastle.Cryptography" Version="2.6.2" />
  </ItemGroup>
</Project>
"""
    path.write_text(content, encoding="utf-8")


def ensure_cs_projects() -> tuple[bool, str]:
    if not tool_exists("dotnet"):
        return False, "dotnet no está instalado."
    write_csproj(CS_CIFRADO_PROJ, "Cifrado")
    write_csproj(CS_DESCIFRADO_PROJ, "Descifrado")
    write_csproj(CS_COMPLETO_PROJ, "Completo")

    sources = sorted(CS_DIR.glob("*.cs"))
    newest = max((src.stat().st_mtime for src in sources if src.exists()), default=0.0)
    newest = max(
        newest,
        CS_CIFRADO_PROJ.stat().st_mtime if CS_CIFRADO_PROJ.exists() else 0.0,
        CS_DESCIFRADO_PROJ.stat().st_mtime if CS_DESCIFRADO_PROJ.exists() else 0.0,
        CS_COMPLETO_PROJ.stat().st_mtime if CS_COMPLETO_PROJ.exists() else 0.0,
    )

    def needs_build(output: Path) -> bool:
        return (not output.exists()) or output.stat().st_mtime < newest

    if needs_build(CS_CIFRADO_DLL):
        proc = run_cmd([
            "dotnet", "build", str(CS_CIFRADO_PROJ),
            "-c", "Release",
            "--nologo",
        ], cwd=ROOT_DIR, timeout=360)
        if proc.returncode != 0:
            return False, proc.stderr[:400] or proc.stdout[:400]

    if needs_build(CS_DESCIFRADO_DLL):
        proc = run_cmd([
            "dotnet", "build", str(CS_DESCIFRADO_PROJ),
            "-c", "Release",
            "--nologo",
        ], cwd=ROOT_DIR, timeout=360)
        if proc.returncode != 0:
            return False, proc.stderr[:400] or proc.stdout[:400]

    if needs_build(CS_COMPLETO_DLL):
        proc = run_cmd([
            "dotnet", "build", str(CS_COMPLETO_PROJ),
            "-c", "Release",
            "--nologo",
        ], cwd=ROOT_DIR, timeout=360)
        if proc.returncode != 0:
            return False, proc.stderr[:400] or proc.stdout[:400]

    return True, ""


def result_error(lang: str, message: str, elapsed_s: float | None = None) -> dict:
    return {
        "lang": lang,
        "size": "?",
        "metrics": [],
        "elapsed_s": elapsed_s,
        "recovery": None,
        "error": message,
    }


def run_parallel_jobs(jobs: list[tuple[str, callable]]) -> list[dict]:
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = {lang: executor.submit(job) for lang, job in jobs}
        for lang, future in futures.items():
            try:
                results[lang] = future.result()
            except Exception as exc:
                results[lang] = result_error(lang, f"Error interno al ejecutar {lang}: {exc}")
    return [results[lang] for lang, _ in jobs]


def finalize_result(lang: str, workdir: Path, original_png: Path, cipher_preview: Path, recovered_png: Path, elapsed_s: float) -> dict:
    img = Image.open(cipher_preview).convert("RGB")
    session_file = next(workdir.glob("*.session.txt"), None)
    session = parse_session_file(session_file) if session_file and session_file.exists() else {}
    recovered_meta = describe_png(recovered_png)
    return {
        "lang": lang,
        "size": f"{img.height}x{img.width}",
        "metrics": compute_metrics(cipher_preview),
        "histogram": compute_histogram(cipher_preview),
        "elapsed_s": round(elapsed_s, 4),
        "wall_s": round(elapsed_s, 4),
        "recovery": compare_recovery(original_png, recovered_png),
        "cipher_img": img_to_b64(cipher_preview),
        "recovered_img": img_to_b64(recovered_png),
        "sha256_output": recovered_meta["sha256_png"],
        "sha256_rgb": recovered_meta["sha256_rgb"],
        "session_file": str(session_file) if session_file else None,
        "cipher_path": session.get("x_cur_path"),
        "prev_path": session.get("x_prev_path"),
        "preview_path": str(cipher_preview),
        "workdir": str(workdir),
    }


def summarize_encryption_result(lang: str, workdir: Path, cipher_preview: Path, session: dict[str, str], elapsed_s: float) -> dict:
    img = Image.open(cipher_preview).convert("RGB")
    return {
        "lang": lang,
        "size": f"{img.height}x{img.width}",
        "metrics": compute_metrics(cipher_preview),
        "histogram": compute_histogram(cipher_preview),
        "elapsed_s": round(elapsed_s, 4),
        "wall_s": round(elapsed_s, 4),
        "recovery": None,
        "cipher_img": img_to_b64(cipher_preview),
        "recovered_img": None,
        "sha256_output": None,
        "sha256_rgb": None,
        "session_file": str(Path(str(session["x_cur_path"]) + ".session.txt")) if "x_cur_path" in session else None,
        "cipher_path": session.get("x_cur_path"),
        "prev_path": session.get("x_prev_path"),
        "preview_path": str(cipher_preview),
        "workdir": str(workdir),
    }


def build_bundle_zip(session_id: str, items: list[tuple[str, list[Path]]]) -> str | None:
    if not items:
        return None
    ensure_session_dirs(session_id)
    filename = unique_name("cipher_bundle", ".zip")
    bundle_path = session_download_root(session_id) / filename
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for label, files in items:
            for child in files:
                if child.exists() and child.is_file():
                    zf.write(child, arcname=f"{label}/{child.name}")
    return filename


def copy_download_file(session_id: str, src: Path, prefix: str, suffix: str) -> str:
    ensure_session_dirs(session_id)
    filename = unique_name(prefix, suffix)
    dst = session_download_root(session_id) / filename
    shutil.copy2(src, dst)
    return filename


def convert_image_file(src: Path, target_format: str, dst: Path) -> Path:
    fmt_key = target_format.lower()
    if fmt_key not in EXPORT_FORMATS:
        raise ValueError("Formato de salida no soportado.")
    pil_format, _suffix, _mime = EXPORT_FORMATS[fmt_key]
    with Image.open(src) as img:
        if pil_format == "JPEG":
            img = img.convert("RGB")
            img.save(dst, format=pil_format, quality=95, optimize=True)
        else:
            img.save(dst, format=pil_format)
    return dst


def export_converted_image(session_id: str, source_name: str, output_name: str, output_format: str) -> tuple[str, str]:
    ensure_session_dirs(session_id)
    fmt_key = output_format.lower()
    if fmt_key not in EXPORT_FORMATS:
        raise ValueError("Formato de salida no soportado.")

    source_path = session_download_root(session_id) / Path(source_name).name
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError("La imagen base para exportación ya no está disponible.")

    pil_format, suffix, _mime = EXPORT_FORMATS[fmt_key]
    safe_name = sanitize_output_name(output_name)
    export_filename = unique_name(safe_name, suffix)
    export_path = session_download_root(session_id) / export_filename

    convert_image_file(source_path, fmt_key, export_path)

    return export_filename, export_filename


def encrypt_c(session_id: str, input_png: Path, steps: int, passphrase: str, shared_session: dict[str, str] | None = None) -> dict:
    del passphrase
    ok, msg = ensure_c_binaries()
    if not ok:
        return result_error("C", msg)

    tmpdir = make_runtime_dir(session_id, "c_")
    out_cipher = tmpdir / "cipher_c.bin"
    out_preview = tmpdir / "cipher_c.png"
    out_recovered = tmpdir / "recovered_c.png"

    t0 = time.perf_counter()
    cmd = [str(C_CIFRADOR), str(input_png), str(out_cipher), str(out_preview), str(steps)]
    if shared_session:
        cmd.extend([shared_session["z_hex"], shared_session["salt_hex"]])
    proc = run_cmd(cmd, cwd=ROOT_DIR, timeout=240)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        return result_error("C", proc.stderr[:400] or proc.stdout[:400], round(wall, 4))

    session = parse_session_file(Path(str(out_cipher) + ".session.txt"))
    return summarize_encryption_result("C", tmpdir, out_preview, session, wall)


def decrypt_c_from_session(session: dict[str, str], out_recovered: Path) -> str | None:
    proc = run_cmd([
        str(C_DESCIFRADOR),
        session["x_prev_path"],
        session["x_cur_path"],
        str(out_recovered),
        session["ancho"],
        session["alto"],
        session["canales"],
        session["rondas"],
        session["z_hex"],
        session["salt_hex"],
    ], cwd=ROOT_DIR, timeout=240)
    if proc.returncode != 0:
        return proc.stderr[:400] or proc.stdout[:400]
    return None


def run_c(session_id: str, input_png: Path, steps: int, passphrase: str, shared_session: dict[str, str] | None = None) -> dict:
    del passphrase
    ok, msg = ensure_c_binaries()
    if not ok:
        return result_error("C", msg)

    tmpdir = make_runtime_dir(session_id, "c_")
    out_cipher = tmpdir / "cipher_c.bin"
    out_preview = tmpdir / "cipher_c.png"
    out_recovered = tmpdir / "recovered_c.png"

    t0 = time.perf_counter()
    cmd = [str(C_COMPLETO), str(input_png), str(out_cipher), str(out_preview), str(out_recovered), str(steps)]
    if shared_session:
        cmd.extend([shared_session["z_hex"], shared_session["salt_hex"]])
    proc = run_cmd(cmd, cwd=ROOT_DIR, timeout=240)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        return result_error("C", proc.stderr[:400] or proc.stdout[:400], round(wall, 4))
    return finalize_result("C", tmpdir, input_png, out_preview, out_recovered, wall)


def encrypt_java(session_id: str, input_png: Path, steps: int, passphrase: str, shared_session: dict[str, str] | None = None) -> dict:
    del passphrase
    ok, msg = ensure_java_build()
    if not ok:
        return result_error("Java", msg)

    tmpdir = make_runtime_dir(session_id, "java_")
    out_cipher = tmpdir / "cipher_java.bin"
    out_preview = tmpdir / "cipher_java.png"
    out_recovered = tmpdir / "recovered_java.png"

    t0 = time.perf_counter()
    cmd = ["java", "-cp", str(JAVA_BUILD_DIR), "Cifrado", str(input_png), str(out_cipher), str(out_preview), str(steps)]
    if shared_session:
        cmd.extend([shared_session["z_hex"], shared_session["salt_hex"]])
    proc = run_cmd(cmd, cwd=ROOT_DIR, timeout=300)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        return result_error("Java", proc.stderr[:400] or proc.stdout[:400], round(wall, 4))

    session = parse_session_file(Path(str(out_cipher) + ".session.txt"))
    return summarize_encryption_result("Java", tmpdir, out_preview, session, wall)


def decrypt_java_from_session(session: dict[str, str], out_recovered: Path) -> str | None:
    proc = run_cmd([
        "java", "-cp", str(JAVA_BUILD_DIR), "Descifrado",
        session["x_prev_path"],
        session["x_cur_path"],
        str(out_recovered),
        session["ancho"],
        session["alto"],
        session["canales"],
        session["rondas"],
        session["z_hex"],
        session["salt_hex"],
    ], cwd=ROOT_DIR, timeout=300)
    if proc.returncode != 0:
        return proc.stderr[:400] or proc.stdout[:400]
    return None


def run_java(session_id: str, input_png: Path, steps: int, passphrase: str, shared_session: dict[str, str] | None = None) -> dict:
    del passphrase
    ok, msg = ensure_java_build()
    if not ok:
        return result_error("Java", msg)

    tmpdir = make_runtime_dir(session_id, "java_")
    out_cipher = tmpdir / "cipher_java.bin"
    out_preview = tmpdir / "cipher_java.png"
    out_recovered = tmpdir / "recovered_java.png"

    t0 = time.perf_counter()
    cmd = ["java", "-cp", str(JAVA_BUILD_DIR), "Completo", str(input_png), str(out_cipher), str(out_preview), str(out_recovered), str(steps)]
    if shared_session:
        cmd.extend([shared_session["z_hex"], shared_session["salt_hex"]])
    proc = run_cmd(cmd, cwd=ROOT_DIR, timeout=300)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        return result_error("Java", proc.stderr[:400] or proc.stdout[:400], round(wall, 4))
    return finalize_result("Java", tmpdir, input_png, out_preview, out_recovered, wall)


def encrypt_cs(session_id: str, input_png: Path, steps: int, passphrase: str, shared_session: dict[str, str] | None = None) -> dict:
    del passphrase
    ok, msg = ensure_cs_projects()
    if not ok:
        return result_error("C#", msg)

    tmpdir = make_runtime_dir(session_id, "cs_")
    out_cipher = tmpdir / "cipher_cs.bin"
    out_preview = tmpdir / "cipher_cs.png"
    out_recovered = tmpdir / "recovered_cs.png"

    t0 = time.perf_counter()
    cmd = ["dotnet", str(CS_CIFRADO_DLL), str(input_png), str(out_cipher), str(out_preview), str(steps)]
    if shared_session:
        cmd.extend([shared_session["z_hex"], shared_session["salt_hex"]])
    proc = run_cmd(cmd, cwd=ROOT_DIR, timeout=360)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        return result_error("C#", proc.stderr[:400] or proc.stdout[:400], round(wall, 4))

    session = parse_session_file(Path(str(out_cipher) + ".session.txt"))
    return summarize_encryption_result("C#", tmpdir, out_preview, session, wall)


def decrypt_cs_from_session(session: dict[str, str], out_recovered: Path) -> str | None:
    proc = run_cmd([
        "dotnet", str(CS_DESCIFRADO_DLL),
        session["x_prev_path"],
        session["x_cur_path"],
        str(out_recovered),
        session["ancho"],
        session["alto"],
        session["canales"],
        session["rondas"],
        session["z_hex"],
        session["salt_hex"],
    ], cwd=ROOT_DIR, timeout=360)
    if proc.returncode != 0:
        return proc.stderr[:400] or proc.stdout[:400]
    return None


def run_cs(session_id: str, input_png: Path, steps: int, passphrase: str, shared_session: dict[str, str] | None = None) -> dict:
    del passphrase
    ok, msg = ensure_cs_projects()
    if not ok:
        return result_error("C#", msg)

    tmpdir = make_runtime_dir(session_id, "cs_")
    out_cipher = tmpdir / "cipher_cs.bin"
    out_preview = tmpdir / "cipher_cs.png"
    out_recovered = tmpdir / "recovered_cs.png"

    t0 = time.perf_counter()
    cmd = [
        "dotnet", str(CS_COMPLETO_DLL),
        str(input_png),
        str(out_cipher),
        str(out_preview),
        str(out_recovered),
        str(steps),
    ]
    if shared_session:
        cmd.extend([shared_session["z_hex"], shared_session["salt_hex"]])
    proc = run_cmd(cmd, cwd=ROOT_DIR, timeout=360)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        return result_error("C#", proc.stderr[:400] or proc.stdout[:400], round(wall, 4))

    return finalize_result("C#", tmpdir, input_png, out_preview, out_recovered, wall)


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/run", methods=["POST"])
def api_run():
    session_id = get_session_id()
    clear_session_artifacts(session_id)

    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    steps = int(request.form.get("steps", 10))
    passphrase = request.form.get("pass", "unused")
    session_mode = request.form.get("session_mode", "independent")
    if session_mode not in {"independent", "shared"}:
        session_mode = "independent"

    f = request.files["image"]
    if not allowed_image_filename(f.filename):
        return jsonify({"error": "Formato no soportado. Usa PNG, BMP o TIFF."}), 400
    original_format = Path(f.filename).suffix.lower().lstrip(".")

    img = Image.open(f.stream).convert("RGB")
    width, height = img.size

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    orig_b64 = base64.b64encode(buf.getvalue()).decode()

    input_png = make_temp_png(session_id)
    try:
        img.save(input_png, format="PNG")
        original_histogram = compute_histogram(input_png)
        shared_session = new_shared_session() if session_mode == "shared" else None
        java_r, c_r, cs_r = run_parallel_jobs([
            ("Java", lambda: run_java(session_id, input_png, steps, passphrase, shared_session)),
            ("C", lambda: run_c(session_id, input_png, steps, passphrase, shared_session)),
            ("C#", lambda: run_cs(session_id, input_png, steps, passphrase, shared_session)),
        ])
    finally:
        try:
            input_png.unlink()
        except OSError:
            pass

    bundle_items: list[tuple[str, list[Path]]] = []
    for result in (java_r, c_r, cs_r):
        if not result.get("error") and result.get("workdir"):
            workdir = Path(result["workdir"])
            rewrite_session_files_in_workdir(workdir, original_format)
            artifacts = collect_bundle_artifacts(result)
            if artifacts:
                bundle_items.append((result["lang"], artifacts))
    bundle_name = build_bundle_zip(session_id, bundle_items)

    response = {
        "mode": "full",
        "image_size": [height, width],
        "steps": steps,
        "session_mode": session_mode,
        "original_img": orig_b64,
        "original_histogram": original_histogram,
        "results": [strip_internal_paths(java_r), strip_internal_paths(c_r), strip_internal_paths(cs_r)],
        "bundle_url": f"/api/download/{bundle_name}" if bundle_name else None,
        "bundle_name": bundle_name,
    }
    return jsonify(response)


@app.route("/api/encrypt-only", methods=["POST"])
def api_encrypt_only():
    session_id = get_session_id()
    clear_session_artifacts(session_id)

    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    steps = int(request.form.get("steps", 10))
    passphrase = request.form.get("pass", "unused")
    session_mode = request.form.get("session_mode", "independent")
    if session_mode not in {"independent", "shared"}:
        session_mode = "independent"

    f = request.files["image"]
    if not allowed_image_filename(f.filename):
        return jsonify({"error": "Formato no soportado. Usa PNG, BMP o TIFF."}), 400
    original_format = Path(f.filename).suffix.lower().lstrip(".")

    img = Image.open(f.stream).convert("RGB")
    width, height = img.size

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    orig_b64 = base64.b64encode(buf.getvalue()).decode()

    input_png = make_temp_png(session_id)
    try:
        img.save(input_png, format="PNG")
        original_histogram = compute_histogram(input_png)
        shared_session = new_shared_session() if session_mode == "shared" else None
        java_r, c_r, cs_r = run_parallel_jobs([
            ("Java", lambda: encrypt_java(session_id, input_png, steps, passphrase, shared_session if session_mode == "shared" else None)),
            ("C", lambda: encrypt_c(session_id, input_png, steps, passphrase, shared_session if session_mode == "shared" else None)),
            ("C#", lambda: encrypt_cs(session_id, input_png, steps, passphrase, shared_session if session_mode == "shared" else None)),
        ])
    finally:
        try:
            input_png.unlink()
        except OSError:
            pass

    bundle_items: list[tuple[str, list[Path]]] = []
    for result in (java_r, c_r, cs_r):
        if not result.get("error") and result.get("workdir"):
            workdir = Path(result["workdir"])
            rewrite_session_files_in_workdir(workdir, original_format)
            artifacts = collect_bundle_artifacts(result)
            if artifacts:
                bundle_items.append((result["lang"], artifacts))
    bundle_name = build_bundle_zip(session_id, bundle_items)

    response = {
        "mode": "encrypt",
        "image_size": [height, width],
        "steps": steps,
        "session_mode": session_mode,
        "original_img": orig_b64,
        "original_histogram": original_histogram,
        "results": [strip_internal_paths(java_r), strip_internal_paths(c_r), strip_internal_paths(cs_r)],
        "bundle_url": f"/api/download/{bundle_name}" if bundle_name else None,
        "bundle_name": bundle_name,
    }
    return jsonify(response)


@app.route("/api/decrypt-only", methods=["POST"])
def api_decrypt_only():
    session_id = get_session_id()
    clear_session_artifacts(session_id)

    tmpdir = make_runtime_dir(session_id, "decrypt_")
    artifact_map: dict[str, dict[str, Path]] = {}
    bundle_name = None

    if "bundle" in request.files and request.files["bundle"].filename:
        bundle_upload = request.files["bundle"]
        bundle_name = bundle_upload.filename
        try:
            artifact_map = extract_bundle_artifacts(bundle_upload, tmpdir)
        except zipfile.BadZipFile:
            return jsonify({"error": "El paquete .zip no es válido o está corrupto."}), 400
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not artifact_map:
            return jsonify({"error": "El paquete .zip no contiene artefactos de cifrado válidos."}), 400
    else:
        required = ("cipher", "prev", "session")
        for key in required:
            if key not in request.files:
                return jsonify({"error": f"Falta el archivo requerido: {key}"}), 400
        cipher_file = tmpdir / request.files["cipher"].filename
        prev_file = tmpdir / request.files["prev"].filename
        session_file = tmpdir / request.files["session"].filename
        request.files["cipher"].save(cipher_file)
        request.files["prev"].save(prev_file)
        request.files["session"].save(session_file)
        shared_artifacts = {
            "cipher": cipher_file,
            "prev": prev_file,
            "session": session_file,
        }
        artifact_map = {
            "Java": dict(shared_artifacts),
            "C": dict(shared_artifacts),
            "C#": dict(shared_artifacts),
        }

    folder_aliases = {
        "Java": ["Java"],
        "C": ["C"],
        "C#": ["C#", "Csharp", "csharp"],
    }

    def resolve_artifacts(language: str) -> dict[str, Path] | None:
        for alias in folder_aliases[language]:
            if alias in artifact_map:
                return artifact_map[alias]
        return None

    def decrypt_language(language: str) -> dict:
        artifacts = resolve_artifacts(language)
        if not artifacts:
            return {
                "lang": language,
                "elapsed_s": 0.0,
                "status": "ERROR",
                "error": "No se encontraron artefactos para esta implementación dentro del paquete proporcionado.",
            }
        missing = [key for key in ("cipher", "prev", "session") if key not in artifacts]
        if missing:
            return {
                "lang": language,
                "elapsed_s": 0.0,
                "status": "ERROR",
                "error": f"Faltan artefactos requeridos para {language}: {', '.join(missing)}.",
            }

        session_data, original_format, output_suffix = build_session_from_artifacts(
            artifacts["session"],
            artifacts["cipher"],
            artifacts["prev"],
        )
        output_label = original_format.upper()
        out_recovered = tmpdir / f"recovered_{language.replace('#', 'sharp').lower()}.png"
        out_exported = tmpdir / f"recovered_{language.replace('#', 'sharp').lower()}{output_suffix}"

        if language == "C":
            ok, msg = ensure_c_binaries()
            err = None if ok else msg
            t0 = time.perf_counter()
            if ok:
                err = decrypt_c_from_session(session_data, out_recovered)
        elif language == "Java":
            ok, msg = ensure_java_build()
            err = None if ok else msg
            t0 = time.perf_counter()
            if ok:
                err = decrypt_java_from_session(session_data, out_recovered)
        else:
            ok, msg = ensure_cs_projects()
            err = None if ok else msg
            t0 = time.perf_counter()
            if ok:
                err = decrypt_cs_from_session(session_data, out_recovered)

        elapsed = round(time.perf_counter() - t0, 4)
        if err:
            return {
                "lang": language,
                "elapsed_s": elapsed,
                "status": "ERROR",
                "error": err,
            }

        convert_image_file(out_recovered, original_format, out_exported)
        meta = describe_png(out_exported)
        download_name = copy_download_file(session_id, out_exported, f"recovered_image_{language.replace('#', 'sharp').lower()}", output_suffix)
        return {
            "lang": language,
            "elapsed_s": elapsed,
            "status": "OK",
            "dimensions": {
                "width": meta["width"],
                "height": meta["height"],
                "channels": meta["channels"],
            },
            "output_format": original_format,
            "output_format_label": output_label,
            "output_size_bytes": meta["png_size_bytes"],
            "sha256_output": meta["sha256_png"],
            "sha256_rgb": meta["sha256_rgb"],
            "recovered_img": img_to_b64(out_exported),
            "download_url": f"/api/download/{download_name}",
            "download_name": download_name,
        }

    results = run_parallel_jobs([
        ("Java", lambda: decrypt_language("Java")),
        ("C", lambda: decrypt_language("C")),
        ("C#", lambda: decrypt_language("C#")),
    ])

    response = {
        "mode": "decrypt",
        "bundle_name": bundle_name,
        "results": results,
    }
    return jsonify(response)


@app.route("/api/health")
def health():
    return jsonify({
        "java": "ready" if JAVA_DIR.exists() and tool_exists("javac") and tool_exists("java") else "not compiled",
        "c": "ready" if C_DIR.exists() and tool_exists("gcc") else "not compiled",
        "csharp": "ready" if CS_DIR.exists() and tool_exists("dotnet") else "not compiled",
    })


@app.route("/api/export-recovered", methods=["POST"])
def api_export_recovered():
    session_id = get_session_id()
    payload = request.get_json(silent=True) or {}
    source_name = str(payload.get("source_name", "")).strip()
    output_name = str(payload.get("output_name", "")).strip()
    output_format = str(payload.get("output_format", "png")).strip().lower()

    if not source_name:
        return jsonify({"error": "No se indicó la imagen base para exportar."}), 400
    if not output_name:
        return jsonify({"error": "Indica un nombre de archivo para la exportación."}), 400
    if output_format not in EXPORT_FORMATS:
        return jsonify({"error": "Formato de salida no soportado."}), 400

    try:
        export_filename, download_name = export_converted_image(session_id, source_name, output_name, output_format)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "No se pudo convertir la imagen al formato solicitado."}), 500

    return jsonify({
        "download_url": f"/api/download/{export_filename}",
        "download_name": download_name,
    })


@app.route("/api/download/<path:filename>")
def api_download(filename: str):
    session_id = get_session_id()
    file_path = session_download_root(session_id) / filename
    if not file_path.exists() or not file_path.is_file():
        abort(404)

    return send_file(file_path, as_attachment=True, download_name=file_path.name)


if __name__ == "__main__":
    print(f"C dir:     {C_DIR}")
    print(f"Java dir:  {JAVA_DIR}")
    print(f"C# dir:    {CS_DIR}")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
