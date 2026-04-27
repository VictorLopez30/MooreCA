#!/usr/bin/env python3
"""
Experimento 1:
Ejecuta el cifrado variando el numero de rondas para C, Java y C# sobre una sola imagen.

Rondas:
1, 5, 10, 15, ..., 50

Salida:
- Carpeta con las imagenes cifradas generadas por cada lenguaje y cada numero de rondas.
- Archivo CSV con tiempo de ejecucion y metricas:
  entropy, chi, corr
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from PIL import Image


ROOT_DIR = Path(__file__).resolve().parent
C_DIR = ROOT_DIR / "c"
JAVA_DIR = ROOT_DIR / "java"
CS_DIR = ROOT_DIR / "cs"
BUILD_DIR = ROOT_DIR / "v2" / "build"
EXPERIMENTS_DIR = ROOT_DIR / "Experimentos"

C_CIFRADOR = BUILD_DIR / "cifrador_c"
JAVA_BUILD_DIR = BUILD_DIR / "java"
CS_CIFRADO_PROJ = BUILD_DIR / "cs" / "Cifrado" / "Cifrado.csproj"
CS_CIFRADO_DLL = BUILD_DIR / "cs" / "Cifrado" / "bin" / "Debug" / "net10.0" / "Cifrado.dll"

ROUNDS = [1] + list(range(5, 100, 5))
ALLOWED_EXTENSIONS = {".png", ".bmp", ".tif", ".tiff"}
DEFAULT_REPETITIONS = 7


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

    return {
        "entropy": entropy,
        "chi": chi,
        "corr": corr,
    }


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
    ], cwd=ROOT_DIR)
    if proc.returncode != 0:
        raise RuntimeError(f"Fallo compilando C:\n{proc.stderr}")


def ensure_java_build() -> None:
    if not tool_exists("javac") or not tool_exists("java"):
        raise RuntimeError("javac/java no estan instalados.")
    JAVA_BUILD_DIR.mkdir(parents=True, exist_ok=True)
    sources = sorted(str(p) for p in JAVA_DIR.glob("*.java"))
    proc = run_cmd(["javac", "-d", str(JAVA_BUILD_DIR), *sources], cwd=ROOT_DIR)
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
    proc = run_cmd(["dotnet", "build", str(CS_CIFRADO_PROJ)], cwd=ROOT_DIR, timeout=900)
    if proc.returncode != 0:
        raise RuntimeError(f"Fallo compilando C#:\n{proc.stderr}")
    if not CS_CIFRADO_DLL.exists():
        raise RuntimeError(f"No se encontro el ensamblado compilado de C#: {CS_CIFRADO_DLL}")


def prepare_environment() -> None:
    ensure_c_binaries()
    ensure_java_build()
    ensure_cs_build()


def run_c_encrypt(image_path: Path, rounds: int, out_image: Path, session: dict[str, str]) -> float:
    with tempfile.TemporaryDirectory(prefix="exp1_c_", dir=ROOT_DIR / "v2") as tmp:
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
        ], cwd=ROOT_DIR, timeout=900)
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            raise RuntimeError(f"Error ejecutando C (rondas={rounds}):\n{proc.stderr or proc.stdout}")
        return elapsed


def run_java_encrypt(image_path: Path, rounds: int, out_image: Path, session: dict[str, str]) -> float:
    with tempfile.TemporaryDirectory(prefix="exp1_java_", dir=ROOT_DIR / "v2") as tmp:
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
        ], cwd=ROOT_DIR, timeout=900)
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            raise RuntimeError(f"Error ejecutando Java (rondas={rounds}):\n{proc.stderr or proc.stdout}")
        return elapsed


def run_cs_encrypt(image_path: Path, rounds: int, out_image: Path, session: dict[str, str]) -> float:
    with tempfile.TemporaryDirectory(prefix="exp1_cs_", dir=ROOT_DIR / "v2") as tmp:
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
        ], cwd=ROOT_DIR, timeout=1200)
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            raise RuntimeError(f"Error ejecutando C# (rondas={rounds}):\n{proc.stderr or proc.stdout}")
        return elapsed


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
    with tempfile.TemporaryDirectory(prefix="exp1_measure_", dir=ROOT_DIR / "v2") as tmp:
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


def create_output_dir(base_name: str | None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dir_name = base_name if base_name else f"experimento1_{stamp}"
    out_dir = EXPERIMENTS_DIR / dir_name
    out_dir.mkdir(parents=True, exist_ok=False)
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ejecuta el experimento 1 variando el numero de rondas para C, Java y C#."
    )
    parser.add_argument("image", help="Ruta de la imagen de entrada (PNG, BMP o TIFF).")
    parser.add_argument(
        "--output-name",
        help="Nombre de la carpeta de salida dentro de Experimentos. Si no se indica, se genera con fecha y hora.",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=DEFAULT_REPETITIONS,
        help=f"Numero de repeticiones medidas por configuracion. Por defecto: {DEFAULT_REPETITIONS}.",
    )
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    validate_input_image(image_path)

    print("Preparando entorno de ejecucion...")
    prepare_environment()

    out_dir = create_output_dir(args.output_name)
    csv_path = out_dir / "resultados.csv"

    rows: list[dict[str, object]] = []
    lang_runners = [
        ("C", run_c_encrypt, 0),
        ("Java", run_java_encrypt, 1),
        ("CSharp", run_cs_encrypt, 1),
    ]

    for rounds in ROUNDS:
        print(f"Procesando rondas={rounds} ...")
        session = new_shared_session()
        for language, runner, warmup_runs in lang_runners:
            lang_dir = out_dir / language / f"rondas_{rounds:02d}"
            lang_dir.mkdir(parents=True, exist_ok=True)
            out_image = lang_dir / f"cifrada_{language.lower()}_r{rounds:02d}.png"

            elapsed_mean, elapsed_stddev = measure_runner(
                runner,
                image_path,
                rounds,
                out_image,
                session,
                args.repetitions,
                warmup_runs,
            )
            metrics = compute_metrics(out_image)

            rows.append({
                "rondas": rounds,
                "lenguaje": language,
                "tiempo_promedio_s": round(elapsed_mean, 6),
                "desviacion_estandar_s": round(elapsed_stddev, 6),
                "entropia": metrics["entropy"],
                "chi_cuadrada": metrics["chi"],
                "correlacion": metrics["corr"],
            })

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "rondas",
                "lenguaje",
                "tiempo_promedio_s",
                "desviacion_estandar_s",
                "entropia",
                "chi_cuadrada",
                "correlacion",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Experimento terminado. Resultados en: {out_dir}")
    print(f"CSV generado: {csv_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
