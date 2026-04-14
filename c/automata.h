#ifndef AUTOMATA_H
#define AUTOMATA_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define AUTOMATA_MOD_BASE 257u

typedef enum {
    BOUNDARY_PERIODIC = 0,
    BOUNDARY_REFLECT = 1,
    BOUNDARY_ADIABATIC = 2
} boundary_mode_t;

typedef struct {
    boundary_mode_t top;
    boundary_mode_t bottom;
    boundary_mode_t left;
    boundary_mode_t right;
} boundary_config_t;

/* Convierte coeficientes Moore [NW,N,NE,E,SE,S,SW,W] a kernel 3x3 con centro=0. */
void automata_kernel_from_moore8(const uint16_t coef[8], int32_t kernel_out[3][3]);

/* Un paso de CA de segundo orden:
 * next = conv(cur_permuted, kernel_selector) - prev (mod 257).
 * selector de kernel: patron ajedrez por canal/ronda para usar dos conjuntos. */
int automata_step_u16(
    const uint16_t *prev_state,
    const uint16_t *cur_permuted,
    uint16_t *next_state,
    uint32_t alto,
    uint32_t ancho,
    uint16_t canales,
    int32_t kernel1[3][3],
    int32_t kernel2[3][3],
    uint32_t round_idx,
    boundary_config_t bc
);

#ifdef __cplusplus
}
#endif

#endif
