#define _POSIX_C_SOURCE 200809L

#include "automata.h"
#include "llaves.h"
#include "permutaciones.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <unistd.h>

static int leer_archivo_binario(const char *ruta, uint8_t **buffer, size_t *tam) {
    FILE *f = fopen(ruta, "rb");
    long sz;
    size_t leidos;

    if (!f || !buffer || !tam) {
        return -1;
    }
    if (fseek(f, 0, SEEK_END) != 0) {
        fclose(f);
        return -2;
    }
    sz = ftell(f);
    if (sz < 0) {
        fclose(f);
        return -3;
    }
    rewind(f);

    *buffer = (uint8_t *)malloc((size_t)sz);
    if (!*buffer) {
        fclose(f);
        return -4;
    }

    leidos = fread(*buffer, 1, (size_t)sz, f);
    fclose(f);
    if (leidos != (size_t)sz) {
        free(*buffer);
        *buffer = NULL;
        return -5;
    }
    *tam = (size_t)sz;
    return 0;
}

static int escribir_u8_binario(const char *ruta, const uint8_t *data, size_t n) {
    FILE *f;
    size_t escritos;

    if (!ruta || !data) {
        return -1;
    }
    f = fopen(ruta, "wb");
    if (!f) {
        return -2;
    }
    escritos = fwrite(data, sizeof(uint8_t), n, f);
    fclose(f);
    return (escritos == n) ? 0 : -3;
}

static int es_extension(const char *ruta, const char *ext) {
    const char *dot;
    if (!ruta || !ext) {
        return 0;
    }
    dot = strrchr(ruta, '.');
    if (!dot) {
        return 0;
    }
    return strcasecmp(dot, ext) == 0;
}

static int quote_shell(const char *in, char *out, size_t out_sz) {
    size_t i, j = 0;
    if (!in || !out || out_sz < 3) {
        return -1;
    }
    out[j++] = '"';
    for (i = 0; in[i] != '\0'; ++i) {
        if (in[i] == '"' || in[i] == '\\') {
            if (j + 2 >= out_sz) {
                return -2;
            }
            out[j++] = '\\';
        } else if ((unsigned char)in[i] < 32) {
            return -3;
        }
        if (j + 1 >= out_sz) {
            return -4;
        }
        out[j++] = in[i];
    }
    if (j + 2 > out_sz) {
        return -5;
    }
    out[j++] = '"';
    out[j] = '\0';
    return 0;
}

static int ffmpeg_raw_rgb24_to_img(
    const char *in_raw_path,
    uint32_t ancho,
    uint32_t alto,
    const char *out_img_path
) {
    char qin[1024], qout[1024], cmd[2800];
    int rc;

    rc = quote_shell(in_raw_path, qin, sizeof(qin));
    if (rc != 0) {
        return -1;
    }
    rc = quote_shell(out_img_path, qout, sizeof(qout));
    if (rc != 0) {
        return -2;
    }
    snprintf(
        cmd, sizeof(cmd),
        "ffmpeg -y -v error -f rawvideo -pix_fmt rgb24 -s %ux%u -i %s %s",
        (unsigned)ancho, (unsigned)alto, qin, qout
    );
    return (system(cmd) == 0) ? 0 : -3;
}

static int crear_tmp_path(char *tmpl, size_t sz) {
    int fd;
    if (!tmpl || sz < 24) {
        return -1;
    }
    snprintf(tmpl, sz, "/tmp/tt_dec_%ld_XXXXXX", (long)getpid());
    fd = mkstemp(tmpl);
    if (fd < 0) {
        return -2;
    }
    close(fd);
    return 0;
}

static int hex_val(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int parse_hex_exact(const char *hex, uint8_t *out, size_t out_len) {
    size_t i;
    if (!hex || !out) {
        return -1;
    }
    if (strlen(hex) != out_len * 2u) {
        return -2;
    }
    for (i = 0; i < out_len; ++i) {
        int hi = hex_val(hex[i * 2]);
        int lo = hex_val(hex[i * 2 + 1]);
        if (hi < 0 || lo < 0) {
            return -3;
        }
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return 0;
}

static boundary_mode_t map_mode(uint8_t b) {
    switch (b % 3u) {
        case 0: return BOUNDARY_PERIODIC;
        case 1: return BOUNDARY_REFLECT;
        default: return BOUNDARY_ADIABATIC;
    }
}

static void boundary_from_round(const llave_ronda_t *rk, boundary_config_t *bc) {
    bc->top = map_mode(rk->kkern[0]);
    bc->bottom = map_mode(rk->kkern[1]);
    bc->left = map_mode(rk->kkern[2]);
    bc->right = map_mode(rk->kkern[3]);
}

static int guardar_salida(
    const char *out_path,
    const uint8_t *img_u8,
    size_t nbytes,
    uint32_t ancho,
    uint32_t alto,
    uint16_t canales
) {
    int rc;

    if (!out_path || !img_u8) {
        return -1;
    }
    if ((es_extension(out_path, ".png") || es_extension(out_path, ".bmp")) && canales == 3) {
        char tmp_raw[128];
        rc = crear_tmp_path(tmp_raw, sizeof(tmp_raw));
        if (rc != 0) {
            return -2;
        }
        rc = escribir_u8_binario(tmp_raw, img_u8, nbytes);
        if (rc != 0) {
            remove(tmp_raw);
            return -3;
        }
        rc = ffmpeg_raw_rgb24_to_img(tmp_raw, ancho, alto, out_path);
        remove(tmp_raw);
        if (rc != 0) {
            return -4;
        }
        return 0;
    }
    return escribir_u8_binario(out_path, img_u8, nbytes);
}

static int descifrar_imagen(
    const uint16_t *x_r_minus_1,
    const uint16_t *x_r,
    uint32_t ancho,
    uint32_t alto,
    uint16_t canales,
    uint16_t rondas,
    const uint8_t z[32],
    const uint8_t salt[32],
    uint8_t **img_u8_out,
    size_t *nbytes_out
) {
    size_t elems = (size_t)ancho * (size_t)alto * (size_t)canales;
    uint16_t *next_state = NULL;
    uint16_t *cur_state = NULL;
    uint16_t *cur_perm = NULL;
    uint16_t *prev_rec = NULL;
    uint8_t *img_u8 = NULL;
    rca_ctx_t ctx;
    llave_sesion_t ses;
    int rc = 0;
    int t;

    if (!x_r_minus_1 || !x_r || !img_u8_out || !nbytes_out) {
        return -1;
    }

    next_state = (uint16_t *)malloc(elems * sizeof(uint16_t));
    cur_state = (uint16_t *)malloc(elems * sizeof(uint16_t));
    cur_perm = (uint16_t *)malloc(elems * sizeof(uint16_t));
    prev_rec = (uint16_t *)malloc(elems * sizeof(uint16_t));
    img_u8 = (uint8_t *)malloc(elems);
    if (!next_state || !cur_state || !cur_perm || !prev_rec || !img_u8) {
        rc = -2;
        goto cleanup;
    }
    memcpy(next_state, x_r, elems * sizeof(uint16_t));
    memcpy(cur_state, x_r_minus_1, elems * sizeof(uint16_t));

    ctx.alto = alto;
    ctx.ancho = ancho;
    ctx.canales = canales;
    ctx.rondas = rondas;
    rc = llaves_derivar_sesion(z, salt, 32, &ctx, &ses);
    if (rc != 0) {
        rc = -3;
        goto cleanup;
    }

    for (t = (int)rondas - 1; t >= 0; --t) {
        llave_ronda_t rk;
        int32_t k1[3][3], k2[3][3];
        boundary_config_t bc;

        rc = llaves_derivar_ronda(&ses, &ctx, (uint32_t)t, &rk);
        if (rc != 0) {
            rc = -4;
            goto cleanup;
        }

        memcpy(cur_perm, cur_state, elems * sizeof(uint16_t));
        rc = permutacion_aplicar_u16_imagen(cur_perm, alto, ancho, canales, rk.perm_index);
        if (rc != 0) {
            rc = -5;
            goto cleanup;
        }

        automata_kernel_from_moore8(rk.coef_moore_1, k1);
        automata_kernel_from_moore8(rk.coef_moore_2, k2);
        boundary_from_round(&rk, &bc);

        /* Inversa de la regla de segundo orden:
         * next = conv(cur_perm) - prev  =>  prev = conv(cur_perm) - next */
        rc = automata_step_u16(next_state, cur_perm, prev_rec, alto, ancho, canales, k1, k2, (uint32_t)t, bc);
        if (rc != 0) {
            rc = -6;
            goto cleanup;
        }

        {
            uint16_t *tmp = next_state;
            next_state = cur_state;
            cur_state = prev_rec;
            prev_rec = tmp;
        }
    }

    /* next_state termina en X0 (lifted). Deshacer lifting: x = X0 - 1 mod 257. */
    {
        size_t i;
        for (i = 0; i < elems; ++i) {
            uint16_t v = next_state[i];
            if (v == 0) {
                img_u8[i] = 255; /* caso limite (no esperado en datos validos) */
            } else {
                img_u8[i] = (uint8_t)(v - 1u);
            }
        }
    }

    *img_u8_out = img_u8;
    *nbytes_out = elems;
    img_u8 = NULL;
    rc = 0;

cleanup:
    free(next_state);
    free(cur_state);
    free(cur_perm);
    free(prev_rec);
    free(img_u8);
    return rc;
}

int main(int argc, char **argv) {
    const char *in_prev_path, *in_cur_path, *out_path;
    const char *z_hex, *salt_hex;
    uint32_t ancho, alto;
    uint16_t canales, rondas;
    uint8_t z[32], salt[32];
    uint8_t *buf_prev = NULL, *buf_cur = NULL, *img_u8 = NULL;
    size_t len_prev = 0, len_cur = 0, out_n = 0, elems;
    int rc;

    if (argc != 10) {
        fprintf(stderr, "Uso: %s <x_r-1_u16.bin> <x_r_u16.bin> <out.png|bmp|raw> <ancho> <alto> <canales> <rondas> <Z_hex_64> <salt_hex_64>\n", argv[0]);
        fprintf(stderr, "Nota: Este esquema de 2o orden requiere dos estados cifrados finales (X_{R-1} y X_R).\n");
        return 1;
    }

    in_prev_path = argv[1];
    in_cur_path = argv[2];
    out_path = argv[3];
    ancho = (uint32_t)strtoul(argv[4], NULL, 10);
    alto = (uint32_t)strtoul(argv[5], NULL, 10);
    canales = (uint16_t)strtoul(argv[6], NULL, 10);
    rondas = (uint16_t)strtoul(argv[7], NULL, 10);
    z_hex = argv[8];
    salt_hex = argv[9];

    if (parse_hex_exact(z_hex, z, 32) != 0 || parse_hex_exact(salt_hex, salt, 32) != 0) {
        fprintf(stderr, "Error: Z_hex o salt_hex invalidos (deben ser 64 hex chars cada uno).\n");
        return 2;
    }

    rc = leer_archivo_binario(in_prev_path, &buf_prev, &len_prev);
    if (rc != 0) {
        fprintf(stderr, "Error leyendo %s: %d\n", in_prev_path, rc);
        return 3;
    }
    rc = leer_archivo_binario(in_cur_path, &buf_cur, &len_cur);
    if (rc != 0) {
        fprintf(stderr, "Error leyendo %s: %d\n", in_cur_path, rc);
        free(buf_prev);
        return 4;
    }

    elems = (size_t)ancho * (size_t)alto * (size_t)canales;
    if (len_prev != elems * sizeof(uint16_t) || len_cur != elems * sizeof(uint16_t)) {
        fprintf(stderr, "Tamano invalido: se esperaban %zu bytes por archivo.\n", elems * sizeof(uint16_t));
        free(buf_prev);
        free(buf_cur);
        return 5;
    }

    rc = descifrar_imagen(
        (const uint16_t *)buf_prev,
        (const uint16_t *)buf_cur,
        ancho, alto, canales, rondas,
        z, salt,
        &img_u8, &out_n
    );
    if (rc != 0) {
        fprintf(stderr, "Error en descifrado: %d\n", rc);
        free(buf_prev);
        free(buf_cur);
        return 6;
    }

    rc = guardar_salida(out_path, img_u8, out_n, ancho, alto, canales);
    if (rc != 0) {
        fprintf(stderr, "Error guardando salida: %d\n", rc);
        free(buf_prev);
        free(buf_cur);
        free(img_u8);
        return 7;
    }

    printf("Descifrado completado.\n");
    printf("Entrada estado previo: %s\n", in_prev_path);
    printf("Entrada estado final: %s\n", in_cur_path);
    printf("Salida imagen: %s\n", out_path);
    printf("Dimensiones: %ux%u x %u, rondas=%u\n", ancho, alto, canales, rondas);

    free(buf_prev);
    free(buf_cur);
    free(img_u8);
    return 0;
}
