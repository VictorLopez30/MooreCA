#!/usr/bin/env python3
from __future__ import annotations

import csv
import math
import os
import shutil
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image


ROOT_DIR = Path(__file__).resolve().parent
C_DIR = ROOT_DIR / "c"
JAVA_DIR = ROOT_DIR / "java"
BUILD_DIR = ROOT_DIR / "v2" / "build"
EXPERIMENTS_DIR = ROOT_DIR / "Experimentos"

C_CIFRADOR = BUILD_DIR / "cifrador_c"
JAVA_BUILD_DIR = BUILD_DIR / "java"
CS_CIFRADO_PROJ = BUILD_DIR / "cs" / "Cifrado" / "Cifrado.csproj"
CS_CIFRADO_DLL = BUILD_DIR / "cs" / "Cifrado" / "bin" / "Debug" / "net10.0" / "Cifrado.dll"

ALLOWED_EXTENSIONS = {".png", ".bmp", ".tif", ".tiff"}
DEFAULT_REPETITIONS = 7
DEFAULT_WARMUP_C = 0
DEFAULT_WARMUP_JAVA = 1
DEFAULT_WARMUP_CSHARP = 1

try:
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE_LANCZOS = Image.LANCZOS


@dataclass(frozen=True)
class LanguageRunner:
    name: str
    warmup_runs: int


LANGUAGE_RUNNERS = (
    LanguageRunner("C", DEFAULT_WARMUP_C),
    LanguageRunner("Java", DEFAULT_WARMUP_JAVA),
    LanguageRunner("CSharp", DEFAULT_WARMUP_CSHARP),
)


def tool_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def validate_input_image(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"No existe la imagen de entrada: {path}")
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("La imagen debe ser PNG, BMP o TIFF.")


def new_shared_session() -> dict[str, str]:
    return {
        "z_hex": os.urandom(32).hex(),
        "salt_hex": os.urandom(32).hex(),
    }


def compute_metrics(image_path: Path) -> dict[str, float]:
    img = Image.open(image_path).convert("RGB")
    data = list(img.tobytes())
    n = len(data)
    if n == 0:
        return {"entropy": 0.0, "chi": 0.0, "corr": 0.0}

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

    return {"entropy": entropy, "chi": chi, "corr": corr}


def ensure_c_binaries() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    if not tool_exists("gcc"):
        raise RuntimeError("gcc no esta instalado.")

    proc = run_cmd([
        "gcc", "-std=c11", "-O2",
        str(C_DIR / "cifrado.c"),
        str(C_DIR / "automata.c"),
        str(C_DIR / "permutaciones.c"),
        str(C_DIR / "llaves.c"),
        "-I", str(C_DIR),
        "-lcrypto",
        "-o", str(C_CIFRADOR),
    ], cwd=ROOT_DIR, timeout=900)
    if proc.returncode != 0:
        raise RuntimeError(f"Fallo compilando C:\n{proc.stderr}")


def ensure_java_build() -> None:
    if not tool_exists("javac") or not tool_exists("java"):
        raise RuntimeError("javac/java no estan instalados.")
    JAVA_BUILD_DIR.mkdir(parents=True, exist_ok=True)
    sources = sorted(str(p) for p in JAVA_DIR.glob("*.java"))
    proc = run_cmd(["javac", "-d", str(JAVA_BUILD_DIR), *sources], cwd=ROOT_DIR, timeout=900)
    if proc.returncode != 0:
        raise RuntimeError(f"Fallo compilando Java:\n{proc.stderr}")


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


def ensure_cs_build() -> None:
    if not tool_exists("dotnet"):
        raise RuntimeError("dotnet no esta instalado.")

    write_csproj(CS_CIFRADO_PROJ, "Cifrado")
    proc = run_cmd(["dotnet", "build", str(CS_CIFRADO_PROJ)], cwd=ROOT_DIR, timeout=1200)
    if proc.returncode != 0:
        raise RuntimeError(f"Fallo compilando C#:\n{proc.stderr}")
    if not CS_CIFRADO_DLL.exists():
        raise RuntimeError(f"No se encontro el ensamblado compilado de C#: {CS_CIFRADO_DLL}")


def prepare_environment() -> None:
    ensure_c_binaries()
    ensure_java_build()
    ensure_cs_build()


def run_c_encrypt(image_path: Path, rounds: int, out_image: Path, session: dict[str, str]) -> float:
    with tempfile.TemporaryDirectory(prefix="exp_c_", dir=ROOT_DIR / "v2") as tmp:
        tmpdir = Path(tmp)
        out_bin = tmpdir / "cipher.bin"
        t0 = time.perf_counter()
        proc = run_cmd([
            str(C_CIFRADOR),
            str(image_path),
            str(out_bin),
            str(out_image),
            str(rounds),
            session["z_hex"],
            session["salt_hex"],
        ], cwd=ROOT_DIR, timeout=1800)
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            raise RuntimeError(f"Error ejecutando C (rondas={rounds}):\n{proc.stderr or proc.stdout}")
        return elapsed


def run_java_encrypt(image_path: Path, rounds: int, out_image: Path, session: dict[str, str]) -> float:
    with tempfile.TemporaryDirectory(prefix="exp_java_", dir=ROOT_DIR / "v2") as tmp:
        tmpdir = Path(tmp)
        out_bin = tmpdir / "cipher.bin"
        t0 = time.perf_counter()
        proc = run_cmd([
            "java", "-cp", str(JAVA_BUILD_DIR), "Cifrado",
            str(image_path),
            str(out_bin),
            str(out_image),
            str(rounds),
            session["z_hex"],
            session["salt_hex"],
        ], cwd=ROOT_DIR, timeout=1800)
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            raise RuntimeError(f"Error ejecutando Java (rondas={rounds}):\n{proc.stderr or proc.stdout}")
        return elapsed


def run_cs_encrypt(image_path: Path, rounds: int, out_image: Path, session: dict[str, str]) -> float:
    with tempfile.TemporaryDirectory(prefix="exp_cs_", dir=ROOT_DIR / "v2") as tmp:
        tmpdir = Path(tmp)
        out_bin = tmpdir / "cipher.bin"
        t0 = time.perf_counter()
        proc = run_cmd([
            "dotnet", str(CS_CIFRADO_DLL),
            str(image_path),
            str(out_bin),
            str(out_image),
            str(rounds),
            session["z_hex"],
            session["salt_hex"],
        ], cwd=ROOT_DIR, timeout=2400)
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            raise RuntimeError(f"Error ejecutando C# (rondas={rounds}):\n{proc.stderr or proc.stdout}")
        return elapsed


def runner_function(language: str):
    if language == "C":
        return run_c_encrypt
    if language == "Java":
        return run_java_encrypt
    if language == "CSharp":
        return run_cs_encrypt
    raise ValueError(f"Lenguaje no soportado: {language}")


def measure_runner(
    runner,
    image_path: Path,
    rounds: int,
    out_image: Path,
    session: dict[str, str],
    repetitions: int,
    warmup_runs: int,
) -> tuple[float, float]:
    if repetitions < 1:
        raise ValueError("El numero de repeticiones debe ser al menos 1.")

    timings: list[float] = []
    with tempfile.TemporaryDirectory(prefix="exp_measure_", dir=ROOT_DIR / "v2") as tmp:
        tmpdir = Path(tmp)
        scratch_image = tmpdir / "scratch.png"

        for _ in range(warmup_runs):
            runner(image_path, rounds, scratch_image, session)

        for rep in range(repetitions):
            target_image = out_image if rep == repetitions - 1 else scratch_image
            timings.append(runner(image_path, rounds, target_image, session))

    mean_time = statistics.fmean(timings)
    stddev_time = statistics.stdev(timings) if len(timings) > 1 else 0.0
    return mean_time, stddev_time


def create_output_dir(prefix: str, base_name: str | None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dir_name = base_name if base_name else f"{prefix}_{stamp}"
    out_dir = EXPERIMENTS_DIR / dir_name
    out_dir.mkdir(parents=True, exist_ok=False)
    return out_dir


def resize_image_to_png(input_path: Path, size: int, output_path: Path) -> tuple[int, int]:
    img = Image.open(input_path).convert("RGB")
    resized = img.resize((size, size), RESAMPLE_LANCZOS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resized.save(output_path, format="PNG")
    return resized.size


def convert_image_to_format(input_path: Path, fmt: str, output_path: Path) -> tuple[int, int]:
    img = Image.open(input_path).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pil_fmt = fmt.upper()
    if pil_fmt == "TIF":
        pil_fmt = "TIFF"
    img.save(output_path, format=pil_fmt)
    return img.size


def write_csv(csv_path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def linear_regression(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    if len(points) < 2:
        return 0.0, 0.0, 0.0

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in points)
    if sxx == 0.0:
        return 0.0, mean_y, 0.0
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in points)
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0.0 else 0.0
    return slope, intercept, r2


def print_output_summary(out_dir: Path, csv_paths: list[Path]) -> None:
    print(f"Experimento terminado. Resultados en: {out_dir}")
    for path in csv_paths:
        print(f"CSV generado: {path}")
