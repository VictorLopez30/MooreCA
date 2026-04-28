#!/usr/bin/env python3
"""
Experimento 5:
Impacto del formato de imagen sobre el tiempo total del sistema.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from experimentos_common import (
    DEFAULT_REPETITIONS,
    LANGUAGE_RUNNERS,
    compute_metrics,
    convert_image_to_format,
    create_output_dir,
    measure_runner,
    new_shared_session,
    prepare_environment,
    print_output_summary,
    runner_function,
    validate_input_image,
    write_csv,
)


DEFAULT_ROUNDS = 10
FORMATS = [("png", ".png"), ("bmp", ".bmp"), ("tiff", ".tiff")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta el experimento 5 comparando formatos PNG, BMP y TIFF.")
    parser.add_argument("image", help="Ruta de la imagen base de entrada (PNG, BMP o TIFF).")
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS, help=f"Numero de rondas. Por defecto: {DEFAULT_ROUNDS}.")
    parser.add_argument("--output-name", help="Nombre de la carpeta de salida dentro de Experimentos.")
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS, help=f"Numero de repeticiones medidas por configuracion. Por defecto: {DEFAULT_REPETITIONS}.")
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    validate_input_image(image_path)
    prepare_environment()

    out_dir = create_output_dir("experimento5", args.output_name)
    csv_path = out_dir / "resultados.csv"
    rows: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="exp5_formats_", dir=Path(__file__).resolve().parent / "v2") as tmp:
        tmpdir = Path(tmp)
        converted_inputs: list[tuple[str, Path, int, int]] = []
        for fmt_name, suffix in FORMATS:
            converted_path = tmpdir / f"input_{fmt_name}{suffix}"
            width, height = convert_image_to_format(image_path, fmt_name, converted_path)
            converted_inputs.append((fmt_name, converted_path, width, height))

        for fmt_name, converted_path, width, height in converted_inputs:
            session = new_shared_session()
            print(f"Procesando formato={fmt_name}, rondas={args.rounds} ...")
            for spec in LANGUAGE_RUNNERS:
                lang_dir = out_dir / spec.name / fmt_name
                lang_dir.mkdir(parents=True, exist_ok=True)
                out_image = lang_dir / f"cifrada_{spec.name.lower()}_{fmt_name}.png"
                elapsed_mean, elapsed_stddev = measure_runner(
                    runner_function(spec.name),
                    converted_path,
                    args.rounds,
                    out_image,
                    session,
                    args.repetitions,
                    spec.warmup_runs,
                )
                metrics = compute_metrics(out_image)
                rows.append({
                    "formato": fmt_name,
                    "ancho": width,
                    "alto": height,
                    "rondas": args.rounds,
                    "lenguaje": spec.name,
                    "tiempo_promedio_s": round(elapsed_mean, 6),
                    "desviacion_estandar_s": round(elapsed_stddev, 6),
                    "entropia": metrics["entropy"],
                    "chi_cuadrada": metrics["chi"],
                    "correlacion": metrics["corr"],
                })

    write_csv(
        csv_path,
        ["formato", "ancho", "alto", "rondas", "lenguaje", "tiempo_promedio_s", "desviacion_estandar_s", "entropia", "chi_cuadrada", "correlacion"],
        rows,
    )
    print_output_summary(out_dir, [csv_path])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
