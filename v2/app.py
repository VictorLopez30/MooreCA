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
JAVA_BUILD_DIR = BUILD_DIR / "java"
CS_CIFRADO_PROJ = BUILD_DIR / "cs" / "Cifrado" / "Cifrado.csproj"
CS_DESCIFRADO_PROJ = BUILD_DIR / "cs" / "Descifrado" / "Descifrado.csproj"
ALLOWED_IMAGE_EXTENSIONS = {".png", ".bmp", ".tif", ".tiff"}


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
        "session_file": str(Path(str(session["x_cur_path"]) + ".session.txt")) if "x_cur_path" in session else None,
        "cipher_path": session.get("x_cur_path"),
        "prev_path": session.get("x_prev_path"),
        "preview_path": str(cipher_preview),
        "workdir": str(workdir),
    }


def build_bundle_zip(session_id: str, items: list[tuple[str, Path]]) -> str | None:
    if not items:
        return None
    ensure_session_dirs(session_id)
    filename = unique_name("cipher_bundle", ".zip")
    bundle_path = session_download_root(session_id) / filename
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for label, folder in items:
            if not folder.exists():
                continue
            for child in folder.iterdir():
                if child.is_file():
                    zf.write(child, arcname=f"{label}/{child.name}")
    return filename


def copy_download_file(session_id: str, src: Path, prefix: str, suffix: str) -> str:
    ensure_session_dirs(session_id)
    filename = unique_name(prefix, suffix)
    dst = session_download_root(session_id) / filename
    shutil.copy2(src, dst)
    return filename


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
    t0 = time.perf_counter()
    enc = encrypt_c(session_id, input_png, steps, passphrase, shared_session)
    if enc.get("error"):
        return enc
    session = parse_session_file(Path(enc["session_file"]))
    out_recovered = Path(enc["workdir"]) / "recovered_c.png"
    err = decrypt_c_from_session(session, out_recovered)
    wall = time.perf_counter() - t0
    if err:
        return result_error("C", err, round(wall, 4))
    return finalize_result("C", Path(enc["workdir"]), input_png, Path(enc["preview_path"]), out_recovered, wall)


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
    t0 = time.perf_counter()
    enc = encrypt_java(session_id, input_png, steps, passphrase, shared_session)
    if enc.get("error"):
        return enc
    session = parse_session_file(Path(enc["session_file"]))
    out_recovered = Path(enc["workdir"]) / "recovered_java.png"
    err = decrypt_java_from_session(session, out_recovered)
    wall = time.perf_counter() - t0
    if err:
        return result_error("Java", err, round(wall, 4))
    return finalize_result("Java", Path(enc["workdir"]), input_png, Path(enc["preview_path"]), out_recovered, wall)


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
    cmd = ["dotnet", "run", "--project", str(CS_CIFRADO_PROJ), "--", str(input_png), str(out_cipher), str(out_preview), str(steps)]
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
        "dotnet", "run", "--project", str(CS_DESCIFRADO_PROJ), "--",
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
    t0 = time.perf_counter()
    enc = encrypt_cs(session_id, input_png, steps, passphrase, shared_session)
    if enc.get("error"):
        return enc
    session = parse_session_file(Path(enc["session_file"]))
    out_recovered = Path(enc["workdir"]) / "recovered_cs.png"
    err = decrypt_cs_from_session(session, out_recovered)
    wall = time.perf_counter() - t0
    if err:
        return result_error("C#", err, round(wall, 4))
    return finalize_result("C#", Path(enc["workdir"]), input_png, Path(enc["preview_path"]), out_recovered, wall)


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

    bundle_items: list[tuple[str, Path]] = []
    for result in (java_r, c_r, cs_r):
        if not result.get("error") and result.get("workdir"):
            bundle_items.append((result["lang"], Path(result["workdir"])))
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

    bundle_items: list[tuple[str, Path]] = []
    for result in (java_r, c_r, cs_r):
        if not result.get("error") and result.get("workdir"):
            bundle_items.append((result["lang"], Path(result["workdir"])))
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

    required = ("cipher", "prev", "session")
    for key in required:
        if key not in request.files:
            return jsonify({"error": f"Falta el archivo requerido: {key}"}), 400

    tmpdir = make_runtime_dir(session_id, "decrypt_")
    cipher_file = tmpdir / request.files["cipher"].filename
    prev_file = tmpdir / request.files["prev"].filename
    session_file = tmpdir / request.files["session"].filename
    request.files["cipher"].save(cipher_file)
    request.files["prev"].save(prev_file)
    request.files["session"].save(session_file)

    base_session = parse_session_file(session_file)
    base_session["x_cur_path"] = str(cipher_file)
    base_session["x_prev_path"] = str(prev_file)

    def decrypt_language(language: str) -> dict:
        session_data = dict(base_session)
        out_recovered = tmpdir / f"recovered_{language.replace('#', 'sharp').lower()}.png"
        t0 = time.perf_counter()

        if language == "C":
            ok, msg = ensure_c_binaries()
            err = None if ok else msg
            if ok:
                err = decrypt_c_from_session(session_data, out_recovered)
        elif language == "Java":
            ok, msg = ensure_java_build()
            err = None if ok else msg
            if ok:
                err = decrypt_java_from_session(session_data, out_recovered)
        else:
            ok, msg = ensure_cs_projects()
            err = None if ok else msg
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

        meta = describe_png(out_recovered)
        download_name = copy_download_file(session_id, out_recovered, f"recovered_image_{language.replace('#', 'sharp').lower()}", ".png")
        return {
            "lang": language,
            "elapsed_s": elapsed,
            "status": "OK",
            "dimensions": {
                "width": meta["width"],
                "height": meta["height"],
                "channels": meta["channels"],
            },
            "png_size_bytes": meta["png_size_bytes"],
            "sha256_png": meta["sha256_png"],
            "sha256_rgb": meta["sha256_rgb"],
            "recovered_img": img_to_b64(out_recovered),
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
