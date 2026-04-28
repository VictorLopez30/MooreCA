#!/usr/bin/env python3
"""
Experimento 6:
Verificacion de cuota computacional.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from experimentos_common import (
    DEFAULT_REPETITIONS,
    LANGUAGE_RUNNERS,
    create_output_dir,
    measure_runner,
    new_shared_session,
    prepare_environment,
    print_output_summary,
    resize_image_to_png,
    runner_function,
    validate_input_image,
    write_csv,
)


DEFAULT_SIZES = [512, 1024, 2048]
DEFAULT_ROUNDS = [10, 20]
DEFAULT_TIME_LIMIT = 5.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta el experimento 6 verificando cuota computacional.")
    parser.add_argument("image", help="Ruta de la imagen de entrada (PNG, BMP o TIFF).")
    parser.add_argument("--sizes", type=int, nargs="+", default=DEFAULT_SIZES, help=f"Lista de tamanos cuadrados. Por defecto: {' '.join(map(str, DEFAULT_SIZES))}.")
    parser.add_argument("--rounds", type=int, nargs="+", default=DEFAULT_ROUNDS, help=f"Lista de rondas. Por defecto: {' '.join(map(str, DEFAULT_ROUNDS))}.")
    parser.add_argument("--time-limit", type=float, default=DEFAULT_TIME_LIMIT, help=f"Cuota maxima de tiempo en segundos. Por defecto: {DEFAULT_TIME_LIMIT}.")
    parser.add_argument("--output-name", help="Nombre de la carpeta de salida dentro de Experimentos.")
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS, help=f"Numero de repeticiones medidas por configuracion. Por defecto: {DEFAULT_REPETITIONS}.")
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    validate_input_image(image_path)
    prepare_environment()

    out_dir = create_output_dir("experimento6", args.output_name)
    csv_path = out_dir / "resultados.csv"
    rows: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="exp6_inputs_", dir=Path(__file__).resolve().parent / "v2") as tmp:
        tmpdir = Path(tmp)
        resized_inputs: dict[int, tuple[Path, int, int]] = {}
        for size in args.sizes:
            resized_input = tmpdir / f"input_{size}.png"
            width, height = resize_image_to_png(image_path, size, resized_input)
            resized_inputs[size] = (resized_input, width, height)

        for size in args.sizes:
            resized_input, width, height = resized_inputs[size]
            for rounds in args.rounds:
                session = new_shared_session()
                print(f"Procesando cuota para tamano={width}x{height}, rondas={rounds}, limite={args.time_limit}s ...")
                for spec in LANGUAGE_RUNNERS:
                    lang_dir = out_dir / spec.name / f"size_{size}" / f"rondas_{rounds}"
                    lang_dir.mkdir(parents=True, exist_ok=True)
                    out_image = lang_dir / f"cifrada_{spec.name.lower()}_{size}_r{rounds}.png"
                    elapsed_mean, elapsed_stddev = measure_runner(
                        runner_function(spec.name),
                        resized_input,
                        rounds,
                        out_image,
                        session,
                        args.repetitions,
                        spec.warmup_runs,
                    )
                    rows.append({
                        "ancho": width,
                        "alto": height,
                        "rondas": rounds,
                        "lenguaje": spec.name,
                        "tiempo_limite_s": args.time_limit,
                        "tiempo_promedio_s": round(elapsed_mean, 6),
                        "desviacion_estandar_s": round(elapsed_stddev, 6),
                        "cumple_cuota": "SI" if elapsed_mean <= args.time_limit else "NO",
                    })

    write_csv(
        csv_path,
        ["ancho", "alto", "rondas", "lenguaje", "tiempo_limite_s", "tiempo_promedio_s", "desviacion_estandar_s", "cumple_cuota"],
        rows,
    )
    print_output_summary(out_dir, [csv_path])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
