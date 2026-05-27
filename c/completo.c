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
    if (!f || !buffer || !tam) return -1;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return -2; }
    sz = ftell(f);
    if (sz < 0) { fclose(f); return -3; }
    rewind(f);
    *buffer = (uint8_t *)malloc((size_t)sz);
    if (!*buffer) { fclose(f); return -4; }
    leidos = fread(*buffer, 1, (size_t)sz, f);
    fclose(f);
    if (leidos != (size_t)sz) { free(*buffer); *buffer = NULL; return -5; }
    *tam = (size_t)sz;
    return 0;
}

static int escribir_u16_binario(const char *ruta, const uint16_t *data, size_t n) {
    FILE *f;
    size_t escritos;
    if (!ruta || !data) return -1;
    f = fopen(ruta, "wb");
    if (!f) return -2;
    escritos = fwrite(data, sizeof(uint16_t), n, f);
    fclose(f);
    return (escritos == n) ? 0 : -3;
}

static int escribir_u8_binario(const char *ruta, const uint8_t *data, size_t n) {
    FILE *f;
    size_t escritos;
    if (!ruta || !data) return -1;
    f = fopen(ruta, "wb");
    if (!f) return -2;
    escritos = fwrite(data, sizeof(uint8_t), n, f);
    fclose(f);
    return (escritos == n) ? 0 : -3;
}

static int bytes_to_hex(const uint8_t *in, size_t in_len, char *out, size_t out_sz) {
    static const char kHex[] = "0123456789abcdef";
    size_t i;
    if (!in || !out || out_sz < (in_len * 2u + 1u)) return -1;
    for (i = 0; i < in_len; ++i) {
        out[i * 2] = kHex[in[i] >> 4];
        out[i * 2 + 1] = kHex[in[i] & 0x0Fu];
    }
    out[in_len * 2u] = '\0';
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
    if (!hex || !out) return -1;
    if (strlen(hex) != out_len * 2u) return -2;
    for (i = 0; i < out_len; ++i) {
        int hi = hex_val(hex[i * 2]);
        int lo = hex_val(hex[i * 2 + 1]);
        if (hi < 0 || lo < 0) return -3;
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return 0;
}

static int guardar_sesion_txt(
    const char *ruta_sesion,
    const char *ruta_x_prev,
    const char *ruta_x_cur,
    uint32_t ancho,
    uint32_t alto,
    uint16_t canales,
    uint16_t rondas,
    const uint8_t z[32],
    const uint8_t salt[32]
) {
    FILE *f;
    char z_hex[65];
    char salt_hex[65];
    if (!ruta_sesion || !ruta_x_prev || !ruta_x_cur || !z || !salt) return -1;
    if (bytes_to_hex(z, 32, z_hex, sizeof(z_hex)) != 0) return -2;
    if (bytes_to_hex(salt, 32, salt_hex, sizeof(salt_hex)) != 0) return -3;
    f = fopen(ruta_sesion, "w");
    if (!f) return -4;
    fprintf(f, "# Sesion de cifrado\n");
    fprintf(f, "ancho=%u\n", (unsigned)ancho);
    fprintf(f, "alto=%u\n", (unsigned)alto);
    fprintf(f, "canales=%u\n", (unsigned)canales);
    fprintf(f, "rondas=%u\n", (unsigned)rondas);
    fprintf(f, "x_prev_path=%s\n", ruta_x_prev);
    fprintf(f, "x_cur_path=%s\n", ruta_x_cur);
    fprintf(f, "z_hex=%s\n", z_hex);
    fprintf(f, "salt_hex=%s\n", salt_hex);
    fclose(f);
    return 0;
}

static int es_extension(const char *ruta, const char *ext) {
    const char *dot;
    if (!ruta || !ext) return 0;
    dot = strrchr(ruta, '.');
    if (!dot) return 0;
    return strcasecmp(dot, ext) == 0;
}

static int quote_shell(const char *in, char *out, size_t out_sz) {
    size_t i, j = 0;
    if (!in || !out || out_sz < 3) return -1;
    out[j++] = '"';
    for (i = 0; in[i] != '\0'; ++i) {
        if (in[i] == '"' || in[i] == '\\') {
            if (j + 2 >= out_sz) return -2;
            out[j++] = '\\';
        } else if ((unsigned char)in[i] < 32) {
            return -3;
        }
        if (j + 1 >= out_sz) return -4;
        out[j++] = in[i];
    }
    if (j + 2 > out_sz) return -5;
    out[j++] = '"';
    out[j] = '\0';
    return 0;
}

static int obtener_dims_imagen(const char *ruta, uint32_t *ancho, uint32_t *alto) {
    char qruta[1024], cmd[1400], line[128];
    FILE *p;
    unsigned w, h;
    int rc;
    if (!ruta || !ancho || !alto) return -1;
    rc = quote_shell(ruta, qruta, sizeof(qruta));
    if (rc != 0) return -2;
    snprintf(cmd, sizeof(cmd), "ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x %s", qruta);
    p = popen(cmd, "r");
    if (!p) return -3;
    if (!fgets(line, sizeof(line), p)) { pclose(p); return -4; }
    if (pclose(p) != 0) return -5;
    if (sscanf(line, "%ux%u", &w, &h) != 2 || w == 0 || h == 0) return -6;
    *ancho = (uint32_t)w;
    *alto = (uint32_t)h;
    return 0;
}

static int ffmpeg_to_raw_rgb24(const char *in_path, const char *out_raw_path) {
    char qin[1024], qout[1024], cmd[2600];
    int rc;
    rc = quote_shell(in_path, qin, sizeof(qin));
    if (rc != 0) return -1;
    rc = quote_shell(out_raw_path, qout, sizeof(qout));
    if (rc != 0) return -2;
    snprintf(cmd, sizeof(cmd), "ffmpeg -y -v error -i %s -f rawvideo -pix_fmt rgb24 %s", qin, qout);
    return (system(cmd) == 0) ? 0 : -3;
}

static int ffmpeg_raw_rgb24_to_img(const char *in_raw_path, uint32_t ancho, uint32_t alto, const char *out_img_path) {
    char qin[1024], qout[1024], cmd[2800];
    int rc;
    rc = quote_shell(in_raw_path, qin, sizeof(qin));
    if (rc != 0) return -1;
    rc = quote_shell(out_img_path, qout, sizeof(qout));
    if (rc != 0) return -2;
    snprintf(cmd, sizeof(cmd), "ffmpeg -y -v error -f rawvideo -pix_fmt rgb24 -s %ux%u -i %s %s", (unsigned)ancho, (unsigned)alto, qin, qout);
    return (system(cmd) == 0) ? 0 : -3;
}

static int crear_tmp_path(char *tmpl, size_t sz) {
    int fd;
    if (!tmpl || sz < 24) return -1;
    snprintf(tmpl, sz, "/tmp/tt_img_%ld_XXXXXX", (long)getpid());
    fd = mkstemp(tmpl);
    if (fd < 0) return -2;
    close(fd);
    return 0;
}

static int es_cero_32(const uint8_t z[32]) {
    size_t i;
    for (i = 0; i < 32; ++i) if (z[i] != 0) return 0;
    return 1;
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

static int cifrar_imagen(
    const uint8_t *img_u8,
    uint32_t alto,
    uint32_t ancho,
    uint16_t canales,
    uint16_t rondas,
    const uint8_t *z_in,
    const uint8_t *salt_in,
    uint16_t **cipher_prev_u16_out,
    uint16_t **cipher_u16_out,
    size_t *cipher_elems_out,
    uint8_t z_out[32],
    uint8_t salt_out[32]
) {
    size_t elems = (size_t)alto * (size_t)ancho * (size_t)canales;
    uint16_t *prev = NULL, *cur = NULL, *cur_perm = NULL, *next = NULL;
    x25519_keypair_t a, b;
    uint8_t z1[32], z2[32];
    uint8_t salt[SALT_RECOMENDADO_BYTES];
    size_t salt_len = 0;
    rca_ctx_t ctx;
    llave_sesion_t ses;
    uint32_t i;
    int rc = 0;
    if (!img_u8 || !cipher_prev_u16_out || !cipher_u16_out || !cipher_elems_out || !z_out || !salt_out || elems == 0) return -1;
    prev = (uint16_t *)calloc(elems, sizeof(uint16_t));
    cur = (uint16_t *)malloc(elems * sizeof(uint16_t));
    cur_perm = (uint16_t *)malloc(elems * sizeof(uint16_t));
    next = (uint16_t *)malloc(elems * sizeof(uint16_t));
    if (!prev || !cur || !cur_perm || !next) { rc = -2; goto cleanup; }
    for (i = 0; i < elems; ++i) cur[i] = (uint16_t)((img_u8[i] + 1u) % AUTOMATA_MOD_BASE);
    if (z_in && salt_in) {
        memcpy(z1, z_in, 32);
        memcpy(salt, salt_in, 32);
        salt_len = 32;
        if (es_cero_32(z1)) { rc = -10; goto cleanup; }
    } else {
        rc = x25519_generar_par(&a); if (rc != 0) { rc = -11; goto cleanup; }
        rc = x25519_generar_par(&b); if (rc != 0) { rc = -12; goto cleanup; }
        rc = x25519_calcular_secreto_compartido(a.sk, b.pk, z1); if (rc != 0) { rc = -13; goto cleanup; }
        rc = x25519_calcular_secreto_compartido(b.sk, a.pk, z2);
        if (rc != 0 || memcmp(z1, z2, 32) != 0 || es_cero_32(z1)) { rc = -14; goto cleanup; }
        rc = llaves_generar_salt(salt, &salt_len); if (rc != 0) { rc = -15; goto cleanup; }
    }
    ctx.alto = alto; ctx.ancho = ancho; ctx.canales = canales; ctx.rondas = rondas;
    rc = llaves_derivar_sesion(z1, salt, salt_len, &ctx, &ses); if (rc != 0) { rc = -16; goto cleanup; }
    for (i = 0; i < (uint32_t)rondas; ++i) {
        llave_ronda_t rk;
        int32_t kernels[3][2][3][3];
        boundary_config_t bc;
        uint32_t ch, kv;
        rc = llaves_derivar_ronda(&ses, &ctx, i, &rk); if (rc != 0) { rc = -21; goto cleanup; }
        memcpy(cur_perm, cur, elems * sizeof(uint16_t));
        rc = permutacion_aplicar_u16_imagen(cur_perm, alto, ancho, canales, rk.perm_index); if (rc != 0) { rc = -22; goto cleanup; }
        for (ch = 0; ch < 3u; ++ch)
            for (kv = 0; kv < 2u; ++kv)
                automata_kernel_from_moore8(rk.coef_moore[ch][kv], kernels[ch][kv]);
        boundary_from_round(&rk, &bc);
        rc = automata_step_u16(prev, cur_perm, next, alto, ancho, canales, kernels, i, bc); if (rc != 0) { rc = -23; goto cleanup; }
        { uint16_t *tmp = prev; prev = cur; cur = next; next = tmp; }
    }
    *cipher_u16_out = cur;
    *cipher_prev_u16_out = prev;
    *cipher_elems_out = elems;
    memcpy(z_out, z1, 32);
    memcpy(salt_out, salt, 32);
    prev = NULL; cur = NULL; rc = 0;
cleanup:
    free(prev); free(cur); free(cur_perm); free(next);
    return rc;
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
    uint16_t *next_state = NULL, *cur_state = NULL, *cur_perm = NULL, *prev_rec = NULL;
    uint8_t *img_u8 = NULL;
    rca_ctx_t ctx;
    llave_sesion_t ses;
    int rc = 0, t;
    if (!x_r_minus_1 || !x_r || !img_u8_out || !nbytes_out) return -1;
    next_state = (uint16_t *)malloc(elems * sizeof(uint16_t));
    cur_state = (uint16_t *)malloc(elems * sizeof(uint16_t));
    cur_perm = (uint16_t *)malloc(elems * sizeof(uint16_t));
    prev_rec = (uint16_t *)malloc(elems * sizeof(uint16_t));
    img_u8 = (uint8_t *)malloc(elems);
    if (!next_state || !cur_state || !cur_perm || !prev_rec || !img_u8) { rc = -2; goto cleanup; }
    memcpy(next_state, x_r, elems * sizeof(uint16_t));
    memcpy(cur_state, x_r_minus_1, elems * sizeof(uint16_t));
    ctx.alto = alto; ctx.ancho = ancho; ctx.canales = canales; ctx.rondas = rondas;
    rc = llaves_derivar_sesion(z, salt, 32, &ctx, &ses); if (rc != 0) { rc = -3; goto cleanup; }
    for (t = (int)rondas - 1; t >= 0; --t) {
        llave_ronda_t rk;
        int32_t kernels[3][2][3][3];
        boundary_config_t bc;
        uint32_t ch, kv;
        rc = llaves_derivar_ronda(&ses, &ctx, (uint32_t)t, &rk); if (rc != 0) { rc = -4; goto cleanup; }
        memcpy(cur_perm, cur_state, elems * sizeof(uint16_t));
        rc = permutacion_aplicar_u16_imagen(cur_perm, alto, ancho, canales, rk.perm_index); if (rc != 0) { rc = -5; goto cleanup; }
        for (ch = 0; ch < 3u; ++ch)
            for (kv = 0; kv < 2u; ++kv)
                automata_kernel_from_moore8(rk.coef_moore[ch][kv], kernels[ch][kv]);
        boundary_from_round(&rk, &bc);
        rc = automata_step_u16(next_state, cur_perm, prev_rec, alto, ancho, canales, kernels, (uint32_t)t, bc); if (rc != 0) { rc = -6; goto cleanup; }
        { uint16_t *tmp = next_state; next_state = cur_state; cur_state = prev_rec; prev_rec = tmp; }
    }
    for (size_t i = 0; i < elems; ++i) {
        uint16_t v = next_state[i];
        img_u8[i] = (v == 0) ? 255 : (uint8_t)(v - 1u);
    }
    *img_u8_out = img_u8;
    *nbytes_out = elems;
    img_u8 = NULL;
cleanup:
    free(next_state); free(cur_state); free(cur_perm); free(prev_rec); free(img_u8);
    return rc;
}

static int guardar_salida(const char *out_path, const uint8_t *img_u8, size_t nbytes, uint32_t ancho, uint32_t alto, uint16_t canales) {
    int rc;
    if (!out_path || !img_u8) return -1;
    if ((es_extension(out_path, ".png") || es_extension(out_path, ".bmp") || es_extension(out_path, ".tif") || es_extension(out_path, ".tiff")) && canales == 3) {
        char tmp_raw[128];
        rc = crear_tmp_path(tmp_raw, sizeof(tmp_raw));
        if (rc != 0) return -2;
        rc = escribir_u8_binario(tmp_raw, img_u8, nbytes);
        if (rc != 0) { remove(tmp_raw); return -3; }
        rc = ffmpeg_raw_rgb24_to_img(tmp_raw, ancho, alto, out_path);
        remove(tmp_raw);
        if (rc != 0) return -4;
        return 0;
    }
    return escribir_u8_binario(out_path, img_u8, nbytes);
}

static int cargar_entrada(const char *input_path, uint8_t **img_bytes, size_t *img_len, uint32_t *ancho, uint32_t *alto, uint16_t *canales) {
    char tmp_raw[128];
    int rc;
    if (!input_path || !img_bytes || !img_len || !ancho || !alto || !canales) return -1;
    rc = obtener_dims_imagen(input_path, ancho, alto);
    if (rc != 0) return -2;
    *canales = 3;
    rc = crear_tmp_path(tmp_raw, sizeof(tmp_raw));
    if (rc != 0) return -3;
    rc = ffmpeg_to_raw_rgb24(input_path, tmp_raw);
    if (rc != 0) { remove(tmp_raw); return -4; }
    rc = leer_archivo_binario(tmp_raw, img_bytes, img_len);
    remove(tmp_raw);
    return rc;
}

int main(int argc, char **argv) {
    const char *input_path, *out_cipher, *out_preview, *out_recovered;
    uint16_t rounds, channels = 3;
    uint32_t width = 0, height = 0;
    uint8_t *img_bytes = NULL, *recovered_u8 = NULL;
    size_t img_len = 0, cipher_elems = 0, recovered_n = 0;
    uint16_t *cipher_prev = NULL, *cipher_cur = NULL;
    uint8_t z[32], salt[32];
    char prev_path[1024], session_path[1024];
    int rc;

    if (argc != 6 && argc != 8) {
        fprintf(stderr, "Uso: %s <in.png|in.bmp|in.tif|in.tiff> <out_cipher_u16.bin> <out_preview.png|bmp|tif|tiff|raw> <out_recovered.png|bmp|tif|tiff|raw> <rondas> [Z_hex_64 salt_hex_64]\n", argv[0]);
        return 1;
    }

    input_path = argv[1];
    out_cipher = argv[2];
    out_preview = argv[3];
    out_recovered = argv[4];
    rounds = (uint16_t)strtoul(argv[5], NULL, 10);

    rc = cargar_entrada(input_path, &img_bytes, &img_len, &width, &height, &channels);
    if (rc != 0) {
        fprintf(stderr, "Error cargando imagen de entrada: %d\n", rc);
        return 2;
    }

    if (argc == 8) {
        if (parse_hex_exact(argv[6], z, 32) != 0 || parse_hex_exact(argv[7], salt, 32) != 0) {
            fprintf(stderr, "Error: Z_hex o salt_hex invalidos.\n");
            free(img_bytes);
            return 3;
        }
        rc = cifrar_imagen(img_bytes, height, width, channels, rounds, z, salt, &cipher_prev, &cipher_cur, &cipher_elems, z, salt);
    } else {
        rc = cifrar_imagen(img_bytes, height, width, channels, rounds, NULL, NULL, &cipher_prev, &cipher_cur, &cipher_elems, z, salt);
    }
    if (rc != 0) {
        fprintf(stderr, "Error en cifrado: %d\n", rc);
        free(img_bytes);
        return 4;
    }

    rc = escribir_u16_binario(out_cipher, cipher_cur, cipher_elems);
    if (rc != 0) {
        fprintf(stderr, "Error guardando cifrado: %d\n", rc);
        free(img_bytes); free(cipher_prev); free(cipher_cur);
        return 5;
    }
    rc = snprintf(prev_path, sizeof(prev_path), "%s.prev.bin", out_cipher);
    if (rc < 0 || (size_t)rc >= sizeof(prev_path)) {
        free(img_bytes); free(cipher_prev); free(cipher_cur);
        return 6;
    }
    if (escribir_u16_binario(prev_path, cipher_prev, cipher_elems) != 0) {
        free(img_bytes); free(cipher_prev); free(cipher_cur);
        return 7;
    }

    uint8_t *preview_u8 = (uint8_t *)malloc(cipher_elems);
    if (!preview_u8) {
        free(img_bytes); free(cipher_prev); free(cipher_cur);
        return 8;
    }
    for (size_t i = 0; i < cipher_elems; ++i) preview_u8[i] = (uint8_t)((cipher_cur[i] > 255u) ? 255u : cipher_cur[i]);
    if (guardar_salida(out_preview, preview_u8, cipher_elems, width, height, channels) != 0) {
        free(img_bytes); free(cipher_prev); free(cipher_cur); free(preview_u8);
        return 9;
    }
    free(preview_u8);

    rc = snprintf(session_path, sizeof(session_path), "%s.session.txt", out_cipher);
    if (rc < 0 || (size_t)rc >= sizeof(session_path)) {
        free(img_bytes); free(cipher_prev); free(cipher_cur);
        return 10;
    }
    if (guardar_sesion_txt(session_path, prev_path, out_cipher, width, height, channels, rounds, z, salt) != 0) {
        free(img_bytes); free(cipher_prev); free(cipher_cur);
        return 11;
    }

    rc = descifrar_imagen(cipher_prev, cipher_cur, width, height, channels, rounds, z, salt, &recovered_u8, &recovered_n);
    if (rc != 0) {
        fprintf(stderr, "Error en descifrado: %d\n", rc);
        free(img_bytes); free(cipher_prev); free(cipher_cur);
        return 12;
    }
    if (guardar_salida(out_recovered, recovered_u8, recovered_n, width, height, channels) != 0) {
        fprintf(stderr, "Error guardando recuperada.\n");
        free(img_bytes); free(cipher_prev); free(cipher_cur); free(recovered_u8);
        return 13;
    }

    printf("Cifrado y descifrado completados.\n");
    printf("Entrada: %s\n", input_path);
    printf("Salida estado mod257 (u16): %s\n", out_cipher);
    printf("Salida estado previo (u16): %s\n", prev_path);
    printf("Archivo de sesion: %s\n", session_path);
    printf("Salida preview recortada (u8): %s\n", out_preview);
    printf("Salida recuperada: %s\n", out_recovered);
    printf("Dimensiones: %ux%u x %u, rondas=%u\n", width, height, channels, rounds);

    free(img_bytes); free(cipher_prev); free(cipher_cur); free(recovered_u8);
    return 0;
}
