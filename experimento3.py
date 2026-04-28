#!/usr/bin/env python3
"""
Experimento 3:
Aproximacion en funcion de N * R.
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
    linear_regression,
    measure_runner,
    new_shared_session,
    prepare_environment,
    print_output_summary,
    resize_image_to_png,
    runner_function,
    validate_input_image,
    write_csv,
)


DEFAULT_SIZES = [256, 512, 1024]
DEFAULT_ROUNDS = [1, 5, 10, 20, 50]


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta el experimento 3 aproximando T en funcion de N*R.")
    parser.add_argument("image", help="Ruta de la imagen de entrada (PNG, BMP o TIFF).")
    parser.add_argument("--sizes", type=int, nargs="+", default=DEFAULT_SIZES, help=f"Lista de tamanos cuadrados. Por defecto: {' '.join(map(str, DEFAULT_SIZES))}.")
    parser.add_argument("--rounds", type=int, nargs="+", default=DEFAULT_ROUNDS, help=f"Lista de rondas. Por defecto: {' '.join(map(str, DEFAULT_ROUNDS))}.")
    parser.add_argument("--output-name", help="Nombre de la carpeta de salida dentro de Experimentos.")
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS, help=f"Numero de repeticiones medidas por configuracion. Por defecto: {DEFAULT_REPETITIONS}.")
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    validate_input_image(image_path)
    prepare_environment()

    out_dir = create_output_dir("experimento3", args.output_name)
    details_csv = out_dir / "resultados_detalle.csv"
    regression_csv = out_dir / "regresion.csv"
    detail_rows: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="exp3_inputs_", dir=Path(__file__).resolve().parent / "v2") as tmp:
        tmpdir = Path(tmp)
        resized_inputs: dict[int, Path] = {}
        resized_meta: dict[int, tuple[int, int, int]] = {}

        for size in args.sizes:
            resized_input = tmpdir / f"input_{size}.png"
            width, height = resize_image_to_png(image_path, size, resized_input)
            n_value = width * height * 3
            resized_inputs[size] = resized_input
            resized_meta[size] = (width, height, n_value)

        for size in args.sizes:
            width, height, n_value = resized_meta[size]
            resized_input = resized_inputs[size]
            for rounds in args.rounds:
                nr_value = n_value * rounds
                session = new_shared_session()
                print(f"Procesando tamano={width}x{height}, rondas={rounds} ...")
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
                    metrics = compute_metrics(out_image)
                    detail_rows.append({
                        "ancho": width,
                        "alto": height,
                        "N": n_value,
                        "rondas": rounds,
                        "N_por_R": nr_value,
                        "lenguaje": spec.name,
                        "tiempo_promedio_s": round(elapsed_mean, 6),
                        "desviacion_estandar_s": round(elapsed_stddev, 6),
                        "entropia": metrics["entropy"],
                        "chi_cuadrada": metrics["chi"],
                        "correlacion": metrics["corr"],
                    })

    regression_rows: list[dict[str, object]] = []
    for spec in LANGUAGE_RUNNERS:
        points = [
            (float(row["N_por_R"]), float(row["tiempo_promedio_s"]))
            for row in detail_rows
            if row["lenguaje"] == spec.name
        ]
        slope, intercept, r2 = linear_regression(points)
        regression_rows.append({
            "lenguaje": spec.name,
            "pendiente_a": slope,
            "intercepto_b": intercept,
            "R2": r2,
        })

    write_csv(
        details_csv,
        ["ancho", "alto", "N", "rondas", "N_por_R", "lenguaje", "tiempo_promedio_s", "desviacion_estandar_s", "entropia", "chi_cuadrada", "correlacion"],
        detail_rows,
    )
    write_csv(regression_csv, ["lenguaje", "pendiente_a", "intercepto_b", "R2"], regression_rows)
    print_output_summary(out_dir, [details_csv, regression_csv])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
