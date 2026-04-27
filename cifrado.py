import numpy as np
import matplotlib.pyplot as plt
from hashlib import sha256
from PIL import Image
import tkinter as tk
from tkinter import filedialog
import datetime
import csv
import os
import re
import secrets
from scipy.stats import entropy as scipy_entropy, pearsonr, chisquare

MOD_BASE = 257
METRICS_CSV = "metrics_generations_p257_lift_genkernels_channels_perm_rows_dynbound_spiral_randrow.csv"
GEN_FOLDER = "gens_p257_lift_genkernels_channels_perm_rows_dynbound_spiral_randrow"
N_RULES = 2
MATRICES_PATH = "matrices.txt"


def _u16_stream(seed_bytes, n):
    out = []
    cur = seed_bytes
    while len(out) < n:
        cur = sha256(cur).digest()
        arr = np.frombuffer(cur, dtype=np.uint16)
        out.extend(arr.tolist())
    return out[:n]


def reduce_mod(arr):
    return (arr.astype(np.int64) % MOD_BASE).astype(np.int64)


def pad_spiral(arr, top_mode, bottom_mode, left_mode, right_mode):
    def line(mode, axis, side):
        if mode == "periodic":
            if axis == 0:
                return arr[-1, :] if side == "top" else arr[0, :]
            else:
                return arr[:, -1] if side == "left" else arr[:, 0]
        elif mode == "reflect":
            if axis == 0:
                return arr[0, :] if side == "top" else arr[-1, :]
            else:
                return arr[:, 0] if side == "left" else arr[:, -1]
        elif mode == "adiabatic":
            if axis == 0:
                return arr[0, :] if side == "top" else arr[-1, :]
            else:
                return arr[:, 0] if side == "left" else arr[:, -1]
        else:
            raise ValueError("Unsupported boundary mode")

    def pad_2d(a2d):
        H, W = a2d.shape
        pad = np.zeros((H + 2, W + 2), dtype=a2d.dtype)
        pad[1:-1, 1:-1] = a2d
        pad[0, 1:-1] = line(top_mode, 0, "top")
        pad[-1, 1:-1] = line(bottom_mode, 0, "bottom")
        pad[1:-1, 0] = line(left_mode, 1, "left")
        pad[1:-1, -1] = line(right_mode, 1, "right")
        pad[0, 0] = pad[0, 1]
        pad[0, -1] = pad[0, -2]
        pad[-1, 0] = pad[-1, 1]
        pad[-1, -1] = pad[-1, -2]
        return pad

    if arr.ndim == 2:
        return pad_2d(arr)
    elif arr.ndim == 3:
        channels = [pad_2d(arr[..., c]) for c in range(arr.shape[2])]
        return np.stack(channels, axis=-1)
    else:
        raise ValueError("Unsupported array dimensions")


def derive_kernel_from_seed(seed_bytes, strategy: str = "moore_balanced") -> np.ndarray:
    MAX_ABS_NEIGH = 4
    s = _u16_stream(seed_bytes, 16)

    center = 0
    neigh = np.zeros(8, dtype=np.int32)
    if strategy == "moore_balanced":
        base = (s[1] % (2 * MAX_ABS_NEIGH + 1)) - MAX_ABS_NEIGH
        base2 = (s[2] % (2 * MAX_ABS_NEIGH + 1)) - MAX_ABS_NEIGH
        base3 = (s[3] % (2 * MAX_ABS_NEIGH + 1)) - MAX_ABS_NEIGH
        base4 = (s[4] % (2 * MAX_ABS_NEIGH + 1)) - MAX_ABS_NEIGH

        neigh[1] = base
        neigh[5] = -base
        neigh[3] = base2
        neigh[7] = -base2
        neigh[0] = base3
        neigh[6] = -base3
        neigh[2] = base4
        neigh[4] = -base4

        noise = [((s[5 + i] % 3) - 1) for i in range(8)]
        neigh = neigh + np.array(noise, dtype=np.int32)

    elif strategy == "random_balanced":
        vals = [((s[1 + i] % (2 * MAX_ABS_NEIGH + 1)) - MAX_ABS_NEIGH) for i in range(8)]
        neigh = np.array(vals, dtype=np.int32)
    else:
        raise ValueError("Estrategia de kernel no soportada")

    neigh = np.abs(neigh)

    NW, N, NE, E, SE, S, SW, W = neigh.tolist()
    kernel = np.array(
        [
            [NW, N, NE],
            [W, center, E],
            [SW, S, SE],
        ],
        dtype=np.int32,
    )
    return kernel


def derive_kernel_sets_for_gen(passphrase: str, gen_idx: int, n_rules: int) -> list:
    kernel_sets = []
    for ch in range(3):
        base_seed = (passphrase + f"|kernel|{gen_idx}|ch{ch}").encode("utf-8")
        kernels_ch = []
        for i in range(n_rules):
            seed = sha256(base_seed + i.to_bytes(2, "big")).digest()
            kernels_ch.append(derive_kernel_from_seed(seed, strategy="moore_balanced"))
        kernel_sets.append(kernels_ch)
    return kernel_sets


def load_permutations(path=MATRICES_PATH):
    if not os.path.exists(path):
        raise FileNotFoundError(f"No se encontro {path}")
    perms = []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("==="):
            mat = []
            for k in range(1, 5):
                parts = re.findall(r"-?\d+", lines[i + k])
                if parts:
                    mat.append([int(p) for p in parts])
            if len(mat) == 4 and all(len(row) == 4 for row in mat):
                flat = [x - 1 for row in mat for x in row]
                perms.append(np.array(flat, dtype=np.int64))
            i += 5
        else:
            i += 1
    return perms


def perm_index_for_gen(passphrase: str, gen_idx: int, n_perms: int) -> int:
    h = sha256((passphrase + f"|perm|{gen_idx}").encode("utf-8")).digest()
    val = int.from_bytes(h[:8], "big", signed=False)
    return val % n_perms


def boundary_for_gen(passphrase: str, gen_idx: int):
    modes = ["periodic", "reflect", "adiabatic"]
    h = sha256((passphrase + f"|bound|{gen_idx}").encode("utf-8")).digest()
    top = modes[h[0] % len(modes)]
    bottom = modes[h[1] % len(modes)]
    left = modes[h[2] % len(modes)]
    right = modes[h[3] % len(modes)]
    return top, bottom, left, right


def apply_permutation_bytes(data_u8: np.ndarray, perm: np.ndarray):
    block = len(perm)
    out = data_u8.copy()
    total_blocks = len(data_u8) // block
    for b in range(total_blocks):
        start = b * block
        block_data = data_u8[start : start + block]
        out[start : start + block] = block_data[perm]
    return out


def moore_convolution(img, kernel, modes):
    top_mode, bottom_mode, left_mode, right_mode = modes
    pad = pad_spiral(img, top_mode, bottom_mode, left_mode, right_mode)
    if img.ndim == 2:
        acc = np.zeros_like(img, dtype=np.int64)
        for dy in range(3):
            for dx in range(3):
                acc += kernel[dy, dx] * pad[dy : dy + img.shape[0], dx : dx + img.shape[1]].astype(np.int64)
        return reduce_mod(acc)
    elif img.ndim == 3:
        acc = np.zeros_like(img, dtype=np.int64)
        for dy in range(3):
            for dx in range(3):
                acc += kernel[dy, dx] * pad[dy : dy + img.shape[0], dx : dx + img.shape[1], :].astype(np.int64)
        return reduce_mod(acc)
    else:
        raise ValueError("Unsupported array dimensions")


def moore_convolution_cycle_channels(img, kernel_sets, assign_maps, modes):
    H, W, C = img.shape
    assert C == 3
    out = np.zeros_like(img, dtype=np.int64)
    for ch in range(3):
        convs = [moore_convolution(img[..., ch], k, modes) for k in kernel_sets[ch]]
        stack = np.stack(convs, axis=0)
        gathered = np.take_along_axis(stack, assign_maps[ch][None, ...], axis=0)
        out[..., ch] = reduce_mod(gathered.squeeze(0))
    return out


def ca_forward_states(img_rgb, steps, n_rules, assign_maps, passphrase, perms):
    seed_state = np.zeros(img_rgb.shape[:2], dtype=np.int64)
    seed_state = np.stack([seed_state, seed_state, seed_state], axis=-1)
    prev = seed_state
    cur = img_rgb.astype(np.int64)

    states = [cur]
    for t in range(steps):
        perm = perms[perm_index_for_gen(passphrase, t, len(perms))]
        flat_cur = cur.reshape(-1)
        cur_perm = apply_permutation_bytes(flat_cur, perm).reshape(cur.shape)

        modes = boundary_for_gen(passphrase, t)
        kernel_sets = derive_kernel_sets_for_gen(passphrase, t, n_rules)
        nxt = reduce_mod(moore_convolution_cycle_channels(cur_perm, kernel_sets, assign_maps, modes) - prev)
        prev, cur = cur, nxt
        states.append(cur)
    return states, prev, cur


def ca_backward_recover(prev_state, cur_state, steps, n_rules, assign_maps, passphrase, perms):
    next_state = cur_state
    cur = prev_state
    for t in reversed(range(steps)):
        perm = perms[perm_index_for_gen(passphrase, t, len(perms))]
        flat_cur = cur.reshape(-1)
        cur_perm = apply_permutation_bytes(flat_cur, perm).reshape(cur.shape)

        modes = boundary_for_gen(passphrase, t)
        kernel_sets = derive_kernel_sets_for_gen(passphrase, t, n_rules)
        prev = reduce_mod(moore_convolution_cycle_channels(cur_perm, kernel_sets, assign_maps, modes) - next_state)
        next_state, cur = cur, prev
    return next_state


def to_display_u8(arr):
    return np.clip(arr, 0, 255).astype(np.uint8)


def to_gray(arr_rgb):
    if arr_rgb.ndim == 3 and arr_rgb.shape[2] == 3:
        return (0.299 * arr_rgb[..., 0] + 0.587 * arr_rgb[..., 1] + 0.114 * arr_rgb[..., 2])
    return arr_rgb.astype(np.float64)


def entropy_bits(img_int):
    counts = np.bincount(img_int.reshape(-1).astype(np.int64), minlength=256).astype(np.float64)
    return float(scipy_entropy(counts, base=2))


def chi_square_uniform(img_int):
    counts = np.bincount(img_int.reshape(-1).astype(np.int64), minlength=256).astype(np.float64)
    total = counts.sum()
    expected = np.full(256, total / 256.0)
    chi, _ = chisquare(counts, expected)
    return float(chi)


def adjacent_corr_mean(img_rgb):
    x = to_gray(img_rgb).astype(np.float64)
    if x.shape[0] < 2 and x.shape[1] < 2:
        return 0.0

    def safe_corr(a, b):
        if a.size < 2:
            return 0.0
        if np.allclose(a, a[0]) or np.allclose(b, b[0]):
            return 0.0
        r, _ = pearsonr(a, b)
        return float(np.clip(r, -1.0, 1.0))

    H = x[:, :-1].reshape(-1)
    Hn = x[:, 1:].reshape(-1)

    V = x[:-1, :].reshape(-1)
    Vn = x[1:, :].reshape(-1)

    D = x[:-1, :-1].reshape(-1)
    Dn = x[1:, 1:].reshape(-1)

    cH = safe_corr(H, Hn)
    cV = safe_corr(V, Vn)
    cD = safe_corr(D, Dn)
    return float((cH + cV + cD) / 3.0)


def log_metrics(csv_path, generation, img_int):
    clipped = to_display_u8(img_int)
    row = {
        "generation": generation,
        "entropy": entropy_bits(clipped),
        "correlation": adjacent_corr_mean(clipped),
        "chi_square": chi_square_uniform(clipped),
    }
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def save_generation_image(folder, generation, img_int):
    os.makedirs(folder, exist_ok=True)
    clipped = to_display_u8(img_int)
    fname = os.path.join(folder, f"gen_{generation:03d}.png")
    Image.fromarray(clipped).save(fname)


def escoger_imagen():
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="Seleccionar imagen",
        filetypes=[
            ("Archivos de imagen", "*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.gif"),
            ("Todos archivos", "*.*"),
        ],
    )
    return path


PASS_PHRASE = "Moore-CA|mixed-boundary|RGB-demo"
STEPS = 300                                                                                                                                     


def build_assign_maps(H, W, n_rules, passphrase):
    maps = []
    for ch in range(3):
        amap = np.zeros((H, W), dtype=np.int64)
        for y in range(H):
            offset = secrets.randbelow(n_rules)
            amap[y, :] = (offset + np.arange(W)) % n_rules
        maps.append(amap)
    return maps


def main():
    ruta = escoger_imagen()
    if not ruta:
        print("No se selecciono ninguna imagen. Saliendo.")
        return

    perms = load_permutations(MATRICES_PATH)
    if not perms:
        print("No se encontraron permutaciones en matrices.txt")
        return
    print(f"{len(perms)} permutaciones cargadas.")

    try:
        img = Image.open(ruta).convert("RGB")
        IMG_RGB = np.array(img, dtype=np.uint8)
        print(f"Imagen cargada: {ruta}, tamano = {IMG_RGB.shape}")
    except Exception as e:
        print("Error al cargar imagen:", e)
        return

    img_lift = reduce_mod(IMG_RGB.astype(np.int64) + 1)

    H, W = IMG_RGB.shape[:2]
    assign_maps = build_assign_maps(H, W, N_RULES, PASS_PHRASE)

    log_metrics(METRICS_CSV, 0, img_lift)
    save_generation_image(GEN_FOLDER, 0, img_lift)

    states, last_prev, last_cur = ca_forward_states(img_lift, STEPS, N_RULES, assign_maps, PASS_PHRASE, perms)
    for idx, state in enumerate(states[1:], start=1):
        log_metrics(METRICS_CSV, idx, state)
        save_generation_image(GEN_FOLDER, idx, state)

    cipher_rgb = states[-1]
    cipher_display = to_display_u8(cipher_rgb)

    recovered_x0 = ca_backward_recover(last_prev, last_cur, STEPS, N_RULES, assign_maps, PASS_PHRASE, perms)
    recovered_display = to_display_u8(recovered_x0)

    ok_exact = np.array_equal(img_lift.astype(np.int64), recovered_x0)
    ok_clipped = np.array_equal(img_lift.astype(np.uint8), recovered_display)
    print(
        f"Recuperacion exacta modulo 257 (lifted, kernels gen/canal + perm + filas aleatorias + frontera espiral dinamica)? {ok_exact}"
    )
    print(f"Recuperacion tras recorte [0,255] (lifted)? {ok_clipped}")

    try:
        Image.fromarray(cipher_display).save(
            "imagen_cifrada_rgb_p257_lift_genkernels_channels_perm_rows_dynbound_spiral_randrow.png"
        )
        Image.fromarray(recovered_display).save(
            "imagen_descifrada_rgb_p257_lift_genkernels_channels_perm_rows_dynbound_spiral_randrow.png"
        )
        print(
            "Guardado: imagen_cifrada_rgb_p257_lift_genkernels_channels_perm_rows_dynbound_spiral_randrow.png, "
            "imagen_descifrada_rgb_p257_lift_genkernels_channels_perm_rows_dynbound_spiral_randrow.png"
        )
    except Exception as e:
        print("Error al guardar:", e)

    fig, ax = plt.subplots(1, 3, figsize=(15, 5))
    ax[0].imshow(to_display_u8(img_lift))
    ax[0].set_title("Original + lifting")
    ax[0].axis("off")
    ax[1].imshow(cipher_display)
    ax[1].set_title("Generacion final")
    ax[1].axis("off")
    ax[2].imshow(recovered_display)
    ax[2].set_title(f"Recuperada (ok={ok_exact})")
    ax[2].axis("off")
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
