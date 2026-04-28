#!/usr/bin/env python3
"""
Experimento 2:
Variacion del tamano de imagen con numero fijo de rondas.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from experimentos_common import (
    DEFAULT_REPETITIONS,
    LANGUAGE_RUNNERS,
    compute_metrics,
    create_output_dir,
    create_output_dir as _create_output_dir,
    measure_runner,
    new_shared_session,
    prepare_environment,
    print_output_summary,
    resize_image_to_png,
    runner_function,
    validate_input_image,
    write_csv,
)


DEFAULT_SIZES = [256, 512, 1024, 2048]
DEFAULT_ROUNDS = 10


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta el experimento 2 variando el tamano de imagen.")
    parser.add_argument("image", help="Ruta de la imagen de entrada (PNG, BMP o TIFF).")
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS, help=f"Numero fijo de rondas. Por defecto: {DEFAULT_ROUNDS}.")
    parser.add_argument("--sizes", type=int, nargs="+", default=DEFAULT_SIZES, help=f"Lista de tamanos cuadrados a evaluar. Por defecto: {' '.join(map(str, DEFAULT_SIZES))}.")
    parser.add_argument("--output-name", help="Nombre de la carpeta de salida dentro de Experimentos.")
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS, help=f"Numero de repeticiones medidas por configuracion. Por defecto: {DEFAULT_REPETITIONS}.")
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    validate_input_image(image_path)
    prepare_environment()

    out_dir = _create_output_dir("experimento2", args.output_name)
    csv_path = out_dir / "resultados.csv"
    rows: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="exp2_inputs_", dir=Path(__file__).resolve().parent / "v2") as tmp:
        tmpdir = Path(tmp)
        for size in args.sizes:
            resized_input = tmpdir / f"input_{size}.png"
            width, height = resize_image_to_png(image_path, size, resized_input)
            n_value = width * height * 3
            session = new_shared_session()
            print(f"Procesando tamano={width}x{height}, rondas={args.rounds} ...")

            for spec in LANGUAGE_RUNNERS:
                lang_dir = out_dir / spec.name / f"size_{size}"
                lang_dir.mkdir(parents=True, exist_ok=True)
                out_image = lang_dir / f"cifrada_{spec.name.lower()}_{size}.png"
                elapsed_mean, elapsed_stddev = measure_runner(
                    runner_function(spec.name),
                    resized_input,
                    args.rounds,
                    out_image,
                    session,
                    args.repetitions,
                    spec.warmup_runs,
                )
                metrics = compute_metrics(out_image)
                rows.append({
                    "ancho": width,
                    "alto": height,
                    "N": n_value,
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
        ["ancho", "alto", "N", "rondas", "lenguaje", "tiempo_promedio_s", "desviacion_estandar_s", "entropia", "chi_cuadrada", "correlacion"],
        rows,
    )
    print_output_summary(out_dir, [csv_path])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
