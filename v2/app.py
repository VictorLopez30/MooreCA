"""
Backend web para comparar las implementaciones de cifrado/descifrado en C, Java y C#.
Usa las versiones mantenidas en ../c, ../java y ../cs.
"""
from __future__ import annotations

import base64
import io
import math
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from PIL import Image

app = Flask(__name__)
CORS(app)

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
C_DIR = ROOT_DIR / "c"
JAVA_DIR = ROOT_DIR / "java"
CS_DIR = ROOT_DIR / "cs"
BUILD_DIR = BASE_DIR / "build"
RESULTS_DIR = BASE_DIR / "Resultados"

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
    }


def run_c(input_png: Path, steps: int, passphrase: str, shared_session: dict[str, str] | None = None) -> dict:
    del passphrase
    ok, msg = ensure_c_binaries()
    if not ok:
        return result_error("C", msg)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tmpdir = Path(tempfile.mkdtemp(prefix="c_", dir=RESULTS_DIR))
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
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        return result_error("C", proc.stderr[:400] or proc.stdout[:400], round(wall, 4))

    return finalize_result("C", tmpdir, input_png, out_preview, out_recovered, wall)


def run_java(input_png: Path, steps: int, passphrase: str, shared_session: dict[str, str] | None = None) -> dict:
    del passphrase
    ok, msg = ensure_java_build()
    if not ok:
        return result_error("Java", msg)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tmpdir = Path(tempfile.mkdtemp(prefix="java_", dir=RESULTS_DIR))
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
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        return result_error("Java", proc.stderr[:400] or proc.stdout[:400], round(wall, 4))

    return finalize_result("Java", tmpdir, input_png, out_preview, out_recovered, wall)


def run_cs(input_png: Path, steps: int, passphrase: str, shared_session: dict[str, str] | None = None) -> dict:
    del passphrase
    ok, msg = ensure_cs_projects()
    if not ok:
        return result_error("C#", msg)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tmpdir = Path(tempfile.mkdtemp(prefix="cs_", dir=RESULTS_DIR))
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
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        return result_error("C#", proc.stderr[:400] or proc.stdout[:400], round(wall, 4))

    return finalize_result("C#", tmpdir, input_png, out_preview, out_recovered, wall)


@app.route("/api/run", methods=["POST"])
def api_run():
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

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False, dir=BASE_DIR) as tmp:
        input_png = Path(tmp.name)
    try:
        img.save(input_png, format="PNG")
        original_histogram = compute_histogram(input_png)
        shared_session = new_shared_session() if session_mode == "shared" else None
        java_r = run_java(input_png, steps, passphrase, shared_session)
        c_r = run_c(input_png, steps, passphrase, shared_session)
        cs_r = run_cs(input_png, steps, passphrase, shared_session)
    finally:
        try:
            input_png.unlink()
        except OSError:
            pass

    return jsonify({
        "image_size": [height, width],
        "steps": steps,
        "session_mode": session_mode,
        "original_img": orig_b64,
        "original_histogram": original_histogram,
        "results": [java_r, c_r, cs_r],
    })


@app.route("/api/health")
def health():
    return jsonify({
        "java": "ready" if JAVA_DIR.exists() and tool_exists("javac") and tool_exists("java") else "not compiled",
        "c": "ready" if C_DIR.exists() and tool_exists("gcc") else "not compiled",
        "csharp": "ready" if CS_DIR.exists() and tool_exists("dotnet") else "not compiled",
    })


if __name__ == "__main__":
    print(f"C dir:     {C_DIR}")
    print(f"Java dir:  {JAVA_DIR}")
    print(f"C# dir:    {CS_DIR}")
    app.run(debug=True, port=5000)
