#!/usr/bin/env python3
"""
Experimento 4:
Comparacion directa entre lenguajes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from experimentos_common import (
    DEFAULT_REPETITIONS,
    LANGUAGE_RUNNERS,
    compute_metrics,
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta el experimento 4 comparando C, Java y C#.")
    parser.add_argument("image", help="Ruta de la imagen de entrada (PNG, BMP o TIFF).")
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS, help=f"Numero de rondas. Por defecto: {DEFAULT_ROUNDS}.")
    parser.add_argument("--session-mode", choices=["shared", "independent"], default="shared", help="Modo de sesion criptografica. Por defecto: shared.")
    parser.add_argument("--output-name", help="Nombre de la carpeta de salida dentro de Experimentos.")
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS, help=f"Numero de repeticiones medidas por configuracion. Por defecto: {DEFAULT_REPETITIONS}.")
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    validate_input_image(image_path)
    prepare_environment()

    out_dir = create_output_dir("experimento4", args.output_name)
    csv_path = out_dir / "resultados.csv"
    rows: list[dict[str, object]] = []

    shared_session = new_shared_session() if args.session_mode == "shared" else None
    for spec in LANGUAGE_RUNNERS:
        session = shared_session if shared_session is not None else new_shared_session()
        print(f"Procesando lenguaje={spec.name}, rondas={args.rounds}, sesion={args.session_mode} ...")
        lang_dir = out_dir / spec.name
        lang_dir.mkdir(parents=True, exist_ok=True)
        out_image = lang_dir / f"cifrada_{spec.name.lower()}_r{args.rounds}.png"
        elapsed_mean, elapsed_stddev = measure_runner(
            runner_function(spec.name),
            image_path,
            args.rounds,
            out_image,
            session,
            args.repetitions,
            spec.warmup_runs,
        )
        metrics = compute_metrics(out_image)
        rows.append({
            "lenguaje": spec.name,
            "rondas": args.rounds,
            "modo_sesion": args.session_mode,
            "tiempo_promedio_s": round(elapsed_mean, 6),
            "desviacion_estandar_s": round(elapsed_stddev, 6),
            "entropia": metrics["entropy"],
            "chi_cuadrada": metrics["chi"],
            "correlacion": metrics["corr"],
        })

    write_csv(
        csv_path,
        ["lenguaje", "rondas", "modo_sesion", "tiempo_promedio_s", "desviacion_estandar_s", "entropia", "chi_cuadrada", "correlacion"],
        rows,
    )
    print_output_summary(out_dir, [csv_path])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
