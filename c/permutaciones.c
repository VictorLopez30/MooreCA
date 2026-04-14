#include "permutaciones.h"

#include <stddef.h>
#include <stdlib.h>
#include <string.h>

typedef enum {
    OP_R = 0,
    OP_L = 1,
    OP_U = 2,
    OP_D = 3
} op_t;

typedef struct {
    op_t op1;
    op_t op2;
} op_pair_t;

static const op_pair_t k_pairs[8] = {
    { OP_R, OP_D },
    { OP_R, OP_U },
    { OP_L, OP_D },
    { OP_L, OP_U },
    { OP_U, OP_R },
    { OP_U, OP_L },
    { OP_D, OP_R },
    { OP_D, OP_L }
};

static int validar_imagen(const void *data, uint32_t alto, uint32_t ancho, uint16_t canales) {
    if (!data || alto == 0 || ancho == 0 || canales == 0) {
        return -1;
    }
    return 0;
}

static size_t idx_elem(uint32_t i, uint32_t j, uint32_t ancho, size_t elem_size) {
    return ((size_t)i * (size_t)ancho + (size_t)j) * elem_size;
}

static int aplicar_op(
    uint8_t *data,
    uint32_t alto,
    uint32_t ancho,
    size_t elem_size,
    op_t op,
    uint8_t n
) {
    size_t total_elems = (size_t)alto * (size_t)ancho;
    size_t total_bytes = total_elems * elem_size;
    uint8_t *tmp;
    uint32_t i, j;

    tmp = (uint8_t *)malloc(total_bytes);
    if (!tmp) {
        return -1;
    }

    for (i = 0; i < alto; ++i) {
        for (j = 0; j < ancho; ++j) {
            uint32_t src_i = i;
            uint32_t src_j = j;
            uint32_t dst_i = i;
            uint32_t dst_j = j;

            switch (op) {
                case OP_R:
                    /* shifted[i][j] = m[i][(j + i + n) % c] */
                    src_j = (uint32_t)(((uint64_t)j + i + n) % ancho);
                    break;
                case OP_L:
                    /* shifted[i][(j + i + n) % c] = m[i][j] */
                    dst_j = (uint32_t)(((uint64_t)j + i + n) % ancho);
                    break;
                case OP_U:
                    /* shifted[i][j] = m[(i + j + n) % r][j] */
                    src_i = (uint32_t)(((uint64_t)i + j + n) % alto);
                    break;
                case OP_D:
                    /* shifted[(i + j + n) % r][j] = m[i][j] */
                    dst_i = (uint32_t)(((uint64_t)i + j + n) % alto);
                    break;
                default:
                    free(tmp);
                    return -2;
            }

            memcpy(
                tmp + idx_elem(dst_i, dst_j, ancho, elem_size),
                data + idx_elem(src_i, src_j, ancho, elem_size),
                elem_size
            );
        }
    }

    memcpy(data, tmp, total_bytes);
    free(tmp);
    return 0;
}

static op_t op_inversa(op_t op) {
    switch (op) {
        case OP_R: return OP_L;
        case OP_L: return OP_R;
        case OP_U: return OP_D;
        case OP_D: return OP_U;
        default:   return op;
    }
}

static int spec_to_ops(const perm_spec_t *spec, op_t *op1, uint8_t *n1, op_t *op2, uint8_t *n2) {
    if (!spec || !op1 || !n1 || !op2 || !n2) {
        return -1;
    }
    if (spec->n_rows > 3 || spec->n_cols > 3) {
        return -2;
    }

    if (spec->orden == PERM_ROWS_THEN_COLS) {
        *op1 = (spec->rows_dir == PERM_ROWS_RIGHT) ? OP_R : OP_L;
        *n1 = spec->n_rows;
        *op2 = (spec->cols_dir == PERM_COLS_DOWN) ? OP_D : OP_U;
        *n2 = spec->n_cols;
    } else if (spec->orden == PERM_COLS_THEN_ROWS) {
        *op1 = (spec->cols_dir == PERM_COLS_DOWN) ? OP_D : OP_U;
        *n1 = spec->n_cols;
        *op2 = (spec->rows_dir == PERM_ROWS_RIGHT) ? OP_R : OP_L;
        *n2 = spec->n_rows;
    } else {
        return -3;
    }

    return 0;
}

int permutacion_decode_128(uint8_t perm_idx, perm_spec_t *spec) {
    uint8_t pair_idx;
    const op_pair_t *pair;

    if (!spec) {
        return -1;
    }
    if (perm_idx >= PERMUTACIONES_CATALOGO) {
        return -2;
    }

    pair_idx = (uint8_t)(perm_idx >> 4);      /* 0..7 */
    spec->n_rows = (uint8_t)(perm_idx & 0x03u);       /* 0..3 */
    spec->n_cols = (uint8_t)((perm_idx >> 2) & 0x03u);/* 0..3 */

    pair = &k_pairs[pair_idx];
    switch (pair->op1) {
        case OP_R:
        case OP_L:
            spec->orden = PERM_ROWS_THEN_COLS;
            spec->rows_dir = (pair->op1 == OP_R) ? PERM_ROWS_RIGHT : PERM_ROWS_LEFT;
            spec->cols_dir = (pair->op2 == OP_D) ? PERM_COLS_DOWN : PERM_COLS_UP;
            break;
        case OP_U:
        case OP_D:
            spec->orden = PERM_COLS_THEN_ROWS;
            spec->cols_dir = (pair->op1 == OP_D) ? PERM_COLS_DOWN : PERM_COLS_UP;
            spec->rows_dir = (pair->op2 == OP_R) ? PERM_ROWS_RIGHT : PERM_ROWS_LEFT;
            break;
        default:
            return -3;
    }

    return 0;
}

int permutacion_aplicar_spec_imagen(
    uint8_t *data,
    uint32_t alto,
    uint32_t ancho,
    uint16_t canales,
    const perm_spec_t *spec
) {
    op_t op1, op2;
    uint8_t n1, n2;
    int rc;

    rc = validar_imagen(data, alto, ancho, canales);
    if (rc != 0) {
        return rc;
    }
    rc = spec_to_ops(spec, &op1, &n1, &op2, &n2);
    if (rc != 0) {
        return -10 + rc;
    }

    /* Se permutan pixeles completos (elem_size = canales) para preservar RGB juntos. */
    rc = aplicar_op(data, alto, ancho, (size_t)canales, op1, n1);
    if (rc != 0) {
        return -20;
    }
    rc = aplicar_op(data, alto, ancho, (size_t)canales, op2, n2);
    if (rc != 0) {
        return -21;
    }

    return 0;
}

int permutacion_aplicar_inversa_spec_imagen(
    uint8_t *data,
    uint32_t alto,
    uint32_t ancho,
    uint16_t canales,
    const perm_spec_t *spec
) {
    op_t op1, op2;
    uint8_t n1, n2;
    int rc;

    rc = validar_imagen(data, alto, ancho, canales);
    if (rc != 0) {
        return rc;
    }
    rc = spec_to_ops(spec, &op1, &n1, &op2, &n2);
    if (rc != 0) {
        return -10 + rc;
    }

    /* Inversa: deshacer en orden inverso con operaciones inversas. */
    rc = aplicar_op(data, alto, ancho, (size_t)canales, op_inversa(op2), n2);
    if (rc != 0) {
        return -20;
    }
    rc = aplicar_op(data, alto, ancho, (size_t)canales, op_inversa(op1), n1);
    if (rc != 0) {
        return -21;
    }

    return 0;
}

int permutacion_aplicar_imagen(
    uint8_t *data,
    uint32_t alto,
    uint32_t ancho,
    uint16_t canales,
    uint8_t perm_idx
) {
    perm_spec_t spec;
    int rc = permutacion_decode_128(perm_idx, &spec);
    if (rc != 0) {
        return rc;
    }
    return permutacion_aplicar_spec_imagen(data, alto, ancho, canales, &spec);
}

int permutacion_aplicar_inversa_imagen(
    uint8_t *data,
    uint32_t alto,
    uint32_t ancho,
    uint16_t canales,
    uint8_t perm_idx
) {
    perm_spec_t spec;
    int rc = permutacion_decode_128(perm_idx, &spec);
    if (rc != 0) {
        return rc;
    }
    return permutacion_aplicar_inversa_spec_imagen(data, alto, ancho, canales, &spec);
}

int permutacion_aplicar_u16_imagen(
    uint16_t *data,
    uint32_t alto,
    uint32_t ancho,
    uint16_t canales,
    uint8_t perm_idx
) {
    perm_spec_t spec;
    int rc = permutacion_decode_128(perm_idx, &spec);
    if (rc != 0) {
        return rc;
    }
    rc = validar_imagen(data, alto, ancho, canales);
    if (rc != 0) {
        return rc;
    }

    {
        op_t op1, op2;
        uint8_t n1, n2;
        rc = spec_to_ops(&spec, &op1, &n1, &op2, &n2);
        if (rc != 0) {
            return -10 + rc;
        }
        rc = aplicar_op((uint8_t *)data, alto, ancho, (size_t)canales * sizeof(uint16_t), op1, n1);
        if (rc != 0) {
            return -20;
        }
        rc = aplicar_op((uint8_t *)data, alto, ancho, (size_t)canales * sizeof(uint16_t), op2, n2);
        if (rc != 0) {
            return -21;
        }
    }

    return 0;
}

int permutacion_aplicar_inversa_u16_imagen(
    uint16_t *data,
    uint32_t alto,
    uint32_t ancho,
    uint16_t canales,
    uint8_t perm_idx
) {
    perm_spec_t spec;
    op_t op1, op2;
    uint8_t n1, n2;
    int rc = permutacion_decode_128(perm_idx, &spec);
    if (rc != 0) {
        return rc;
    }
    rc = validar_imagen(data, alto, ancho, canales);
    if (rc != 0) {
        return rc;
    }
    rc = spec_to_ops(&spec, &op1, &n1, &op2, &n2);
    if (rc != 0) {
        return -10 + rc;
    }

    rc = aplicar_op((uint8_t *)data, alto, ancho, (size_t)canales * sizeof(uint16_t), op_inversa(op2), n2);
    if (rc != 0) {
        return -20;
    }
    rc = aplicar_op((uint8_t *)data, alto, ancho, (size_t)canales * sizeof(uint16_t), op_inversa(op1), n1);
    if (rc != 0) {
        return -21;
    }

    return 0;
}
