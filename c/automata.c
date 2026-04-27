#include "automata.h"

#include <stddef.h>

static int32_t mod257(int64_t x) {
    int64_t r = x % (int64_t)AUTOMATA_MOD_BASE;
    if (r < 0) {
        r += AUTOMATA_MOD_BASE;
    }
    return (int32_t)r;
}

static int clamp_index(int idx, int max) {
    if (idx < 0) {
        return 0;
    }
    if (idx >= max) {
        return max - 1;
    }
    return idx;
}

static int wrap_index(int idx, int max) {
    int r = idx % max;
    if (r < 0) {
        r += max;
    }
    return r;
}

static int map_y(int y, int h, boundary_config_t bc) {
    if (y >= 0 && y < h) {
        return y;
    }
    if (y < 0) {
        if (bc.top == BOUNDARY_PERIODIC) {
            return wrap_index(y, h);
        }
        return clamp_index(y, h);
    }
    if (bc.bottom == BOUNDARY_PERIODIC) {
        return wrap_index(y, h);
    }
    return clamp_index(y, h);
}

static int map_x(int x, int w, boundary_config_t bc) {
    if (x >= 0 && x < w) {
        return x;
    }
    if (x < 0) {
        if (bc.left == BOUNDARY_PERIODIC) {
            return wrap_index(x, w);
        }
        return clamp_index(x, w);
    }
    if (bc.right == BOUNDARY_PERIODIC) {
        return wrap_index(x, w);
    }
    return clamp_index(x, w);
}

static size_t idx3(uint32_t y, uint32_t x, uint16_t c, uint32_t w, uint16_t channels) {
    return ((size_t)y * (size_t)w + (size_t)x) * (size_t)channels + (size_t)c;
}

void automata_kernel_from_moore8(const uint16_t coef[8], int32_t kernel_out[3][3]) {
    kernel_out[0][0] = (int32_t)coef[0];
    kernel_out[0][1] = (int32_t)coef[1];
    kernel_out[0][2] = (int32_t)coef[2];
    kernel_out[1][0] = (int32_t)coef[7];
    kernel_out[1][1] = 0;
    kernel_out[1][2] = (int32_t)coef[3];
    kernel_out[2][0] = (int32_t)coef[6];
    kernel_out[2][1] = (int32_t)coef[5];
    kernel_out[2][2] = (int32_t)coef[4];
}

static int32_t (*select_kernel(
    uint32_t y, uint32_t x, uint16_t c, uint32_t round_idx,
    int32_t kernels[AUTOMATA_KERNEL_CHANNELS][AUTOMATA_KERNEL_VARIANTS][3][3]
))[3] {
    uint32_t channel_idx = ((uint32_t)c) % AUTOMATA_KERNEL_CHANNELS;
    uint32_t pick = (y + x + (uint32_t)c + round_idx) & 1u;
    return kernels[channel_idx][pick];
}

int automata_step_u16(
    const uint16_t *prev_state,
    const uint16_t *cur_permuted,
    uint16_t *next_state,
    uint32_t alto,
    uint32_t ancho,
    uint16_t canales,
    int32_t kernels[AUTOMATA_KERNEL_CHANNELS][AUTOMATA_KERNEL_VARIANTS][3][3],
    uint32_t round_idx,
    boundary_config_t bc
) {
    uint32_t y, x;
    uint16_t c;

    if (!prev_state || !cur_permuted || !next_state || !kernels) {
        return -1;
    }
    if (alto == 0 || ancho == 0 || canales == 0) {
        return -2;
    }

    for (y = 0; y < alto; ++y) {
        for (x = 0; x < ancho; ++x) {
            for (c = 0; c < canales; ++c) {
                int dy, dx;
                int64_t acc = 0;
                int32_t (*k)[3] = select_kernel(y, x, c, round_idx, kernels);

                for (dy = -1; dy <= 1; ++dy) {
                    for (dx = -1; dx <= 1; ++dx) {
                        int ny = map_y((int)y + dy, (int)alto, bc);
                        int nx = map_x((int)x + dx, (int)ancho, bc);
                        int32_t kv = k[dy + 1][dx + 1];
                        uint16_t pv = cur_permuted[idx3((uint32_t)ny, (uint32_t)nx, c, ancho, canales)];
                        acc += (int64_t)kv * (int64_t)pv;
                    }
                }

                {
                    size_t pos = idx3(y, x, c, ancho, canales);
                    int32_t conv = mod257(acc);
                    int32_t nxt = mod257((int64_t)conv - (int64_t)prev_state[pos]);
                    next_state[pos] = (uint16_t)nxt;
                }
            }
        }
    }

    return 0;
}
