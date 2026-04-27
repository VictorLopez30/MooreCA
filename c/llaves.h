#ifndef LLAVES_H
#define LLAVES_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LLAVE_BYTES 32
#define HKDF_SHA256_HASHLEN 32
#define X25519_KEY_BYTES 32
#define SALT_RECOMENDADO_BYTES 32

typedef struct {
    uint32_t alto;
    uint32_t ancho;
    uint16_t canales;
    uint16_t rondas;
} rca_ctx_t;

typedef struct {
    uint8_t sk[X25519_KEY_BYTES];
    uint8_t pk[X25519_KEY_BYTES];
} x25519_keypair_t;

typedef struct {
    uint8_t z[LLAVE_BYTES];
    uint8_t salt[SALT_RECOMENDADO_BYTES];
    size_t salt_len;
    uint8_t prk[HKDF_SHA256_HASHLEN];
    uint8_t kperm_base[LLAVE_BYTES];
    uint8_t kkern_base[LLAVE_BYTES];
    uint8_t kmac[LLAVE_BYTES];
    uint8_t kseed[LLAVE_BYTES];
} llave_sesion_t;

typedef struct {
    uint8_t kperm[LLAVE_BYTES];
    uint8_t kkern[LLAVE_BYTES];
    uint8_t perm_index;
    uint16_t coef_moore[3][2][8];
} llave_ronda_t;

void x25519_clamp_private(uint8_t sk[X25519_KEY_BYTES]);
int x25519_generar_par(x25519_keypair_t *kp);
int x25519_calcular_secreto_compartido(
    const uint8_t sk_local[X25519_KEY_BYTES],
    const uint8_t pk_remota[X25519_KEY_BYTES],
    uint8_t z_out[X25519_KEY_BYTES]
);

int llaves_generar_salt(uint8_t salt[SALT_RECOMENDADO_BYTES], size_t *salt_len);
int llaves_derivar_sesion(
    const uint8_t z[X25519_KEY_BYTES],
    const uint8_t *salt, size_t salt_len,
    const rca_ctx_t *ctx,
    llave_sesion_t *ses
);
int llaves_derivar_ronda(
    const llave_sesion_t *ses,
    const rca_ctx_t *ctx,
    uint32_t round_idx,
    llave_ronda_t *out
);
int llaves_derivar_nonce96_drbg(const rca_ctx_t *ctx, uint8_t nonce96[12]);

#ifdef __cplusplus
}
#endif

#endif
