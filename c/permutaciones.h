#ifndef PERMUTACIONES_H
#define PERMUTACIONES_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* 128 permutaciones = 2 (dir filas) * 2 (dir columnas) * 4 (n_filas)
 * * 4 (n_columnas) * 2 (orden de aplicacion). */
#define PERMUTACIONES_CATALOGO 128u

typedef enum {
    PERM_ROWS_THEN_COLS = 0,
    PERM_COLS_THEN_ROWS = 1
} perm_orden_t;

typedef enum {
    PERM_ROWS_LEFT = 0,
    PERM_ROWS_RIGHT = 1
} perm_rows_dir_t;

typedef enum {
    PERM_COLS_UP = 0,
    PERM_COLS_DOWN = 1
} perm_cols_dir_t;

typedef struct {
    perm_rows_dir_t rows_dir;
    perm_cols_dir_t cols_dir;
    uint8_t n_rows;   /* 0..3 */
    uint8_t n_cols;   /* 0..3 */
    perm_orden_t orden;
} perm_spec_t;

/* Decodifica un indice de 0..127 en una especificacion concreta. */
int permutacion_decode_128(uint8_t perm_idx, perm_spec_t *spec);

/* Aplica una permutacion del catalogo sobre una imagen intercalada (H x W x C).
 * data se modifica in-place. */
int permutacion_aplicar_imagen(
    uint8_t *data,
    uint32_t alto,
    uint32_t ancho,
    uint16_t canales,
    uint8_t perm_idx
);

/* Aplica la inversa de la permutacion del catalogo. */
int permutacion_aplicar_inversa_imagen(
    uint8_t *data,
    uint32_t alto,
    uint32_t ancho,
    uint16_t canales,
    uint8_t perm_idx
);

/* Versiones por especificacion (utiles si la llave ya decodifico el indice). */
int permutacion_aplicar_spec_imagen(
    uint8_t *data,
    uint32_t alto,
    uint32_t ancho,
    uint16_t canales,
    const perm_spec_t *spec
);

int permutacion_aplicar_inversa_spec_imagen(
    uint8_t *data,
    uint32_t alto,
    uint32_t ancho,
    uint16_t canales,
    const perm_spec_t *spec
);

/* Misma permutacion pero sobre estados uint16 (util para modulo 257). */
int permutacion_aplicar_u16_imagen(
    uint16_t *data,
    uint32_t alto,
    uint32_t ancho,
    uint16_t canales,
    uint8_t perm_idx
);

int permutacion_aplicar_inversa_u16_imagen(
    uint16_t *data,
    uint32_t alto,
    uint32_t ancho,
    uint16_t canales,
    uint8_t perm_idx
);

#ifdef __cplusplus
}
#endif

#endif
