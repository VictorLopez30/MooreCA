#include "llaves.h"

#include <openssl/evp.h>
#include <openssl/hmac.h>
#include <openssl/rand.h>
#include <openssl/sha.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define INFO_SUITE_MAX 64
#define RCA_P 257u

static void store_le16(uint8_t out[2], uint16_t v) {
    out[0] = (uint8_t)(v & 0xFFu);
    out[1] = (uint8_t)((v >> 8) & 0xFFu);
}

static void store_le32(uint8_t out[4], uint32_t v) {
    out[0] = (uint8_t)(v & 0xFFu);
    out[1] = (uint8_t)((v >> 8) & 0xFFu);
    out[2] = (uint8_t)((v >> 16) & 0xFFu);
    out[3] = (uint8_t)((v >> 24) & 0xFFu);
}

static uint16_t load_le16(const uint8_t in[2]) {
    return (uint16_t)in[0] | ((uint16_t)in[1] << 8);
}

#ifdef LLAVES_DEMO
static void print_hex(const char *label, const uint8_t *buf, size_t len) {
    size_t i;
    printf("%s (%zu B): ", label, len);
    for (i = 0; i < len; ++i) {
        printf("%02x", buf[i]);
    }
    printf("\n");
}
#endif

static int random_bytes(uint8_t *out, size_t len) {
    if (RAND_bytes(out, (int)len) != 1) {
        return -1;
    }
    return 0;
}

void x25519_clamp_private(uint8_t sk[X25519_KEY_BYTES]) {
    sk[0] &= 248u;
    sk[31] &= 127u;
    sk[31] |= 64u;
}

static int x25519_public_from_private(const uint8_t sk[32], uint8_t pk[32]) {
    EVP_PKEY *pkey = NULL;
    size_t pk_len = 32;
    int ok = 0;

    pkey = EVP_PKEY_new_raw_private_key(EVP_PKEY_X25519, NULL, sk, 32);
    if (!pkey) {
        goto cleanup;
    }
    if (EVP_PKEY_get_raw_public_key(pkey, pk, &pk_len) != 1 || pk_len != 32) {
        goto cleanup;
    }
    ok = 1;

cleanup:
    EVP_PKEY_free(pkey);
    return ok ? 0 : -1;
}

int x25519_generar_par(x25519_keypair_t *kp) {
    if (!kp) {
        return -1;
    }
    if (random_bytes(kp->sk, sizeof(kp->sk)) != 0) {
        return -2;
    }
    x25519_clamp_private(kp->sk);
    if (x25519_public_from_private(kp->sk, kp->pk) != 0) {
        return -3;
    }
    return 0;
}

int x25519_calcular_secreto_compartido(
    const uint8_t sk_local[32],
    const uint8_t pk_remota[32],
    uint8_t z_out[32]
) {
    EVP_PKEY *sk = NULL;
    EVP_PKEY *pk = NULL;
    EVP_PKEY_CTX *ctx = NULL;
    size_t z_len = 32;
    int ok = 0;

    sk = EVP_PKEY_new_raw_private_key(EVP_PKEY_X25519, NULL, sk_local, 32);
    pk = EVP_PKEY_new_raw_public_key(EVP_PKEY_X25519, NULL, pk_remota, 32);
    if (!sk || !pk) {
        goto cleanup;
    }

    ctx = EVP_PKEY_CTX_new(sk, NULL);
    if (!ctx) {
        goto cleanup;
    }
    if (EVP_PKEY_derive_init(ctx) != 1) {
        goto cleanup;
    }
    if (EVP_PKEY_derive_set_peer(ctx, pk) != 1) {
        goto cleanup;
    }
    if (EVP_PKEY_derive(ctx, z_out, &z_len) != 1 || z_len != 32) {
        goto cleanup;
    }
    ok = 1;

cleanup:
    EVP_PKEY_CTX_free(ctx);
    EVP_PKEY_free(pk);
    EVP_PKEY_free(sk);
    return ok ? 0 : -1;
}

static int hmac_sha256(
    const uint8_t *key, size_t key_len,
    const uint8_t *msg, size_t msg_len,
    uint8_t out[32]
) {
    unsigned int out_len = 0;
    if (!HMAC(EVP_sha256(), key, (int)key_len, msg, msg_len, out, &out_len)) {
        return -1;
    }
    return (out_len == 32) ? 0 : -1;
}

static int sha256_bytes(const uint8_t *in, size_t in_len, uint8_t out[32]) {
    if (!SHA256(in, in_len, out)) {
        return -1;
    }
    return 0;
}

static int hkdf_extract_sha256(
    const uint8_t *salt, size_t salt_len,
    const uint8_t *ikm, size_t ikm_len,
    uint8_t prk_out[32]
) {
    uint8_t zero_salt[32] = {0};
    const uint8_t *real_salt = salt;
    size_t real_salt_len = salt_len;

    if (!ikm || !prk_out) {
        return -1;
    }
    if (!real_salt || real_salt_len == 0) {
        real_salt = zero_salt;
        real_salt_len = sizeof(zero_salt);
    }
    return hmac_sha256(real_salt, real_salt_len, ikm, ikm_len, prk_out);
}

static int hkdf_expand_sha256(
    const uint8_t prk[32],
    const uint8_t *info, size_t info_len,
    uint8_t *okm, size_t okm_len
) {
    uint8_t t[32];
    uint8_t block[32 + INFO_SUITE_MAX + 1];
    size_t t_len = 0;
    size_t produced = 0;
    uint8_t counter = 1;

    if (!prk || !okm) {
        return -1;
    }
    if (okm_len == 0) {
        return 0;
    }
    if (info_len > INFO_SUITE_MAX) {
        return -2;
    }

    while (produced < okm_len) {
        size_t block_len = 0;
        size_t copy_len;

        if (counter == 0) {
            return -3; 
        }

        if (t_len > 0) {
            memcpy(block + block_len, t, t_len);
            block_len += t_len;
        }
        if (info && info_len > 0) {
            memcpy(block + block_len, info, info_len);
            block_len += info_len;
        }
        block[block_len++] = counter;

        if (hmac_sha256(prk, 32, block, block_len, t) != 0) {
            return -4;
        }
        t_len = sizeof(t);

        copy_len = okm_len - produced;
        if (copy_len > sizeof(t)) {
            copy_len = sizeof(t);
        }
        memcpy(okm + produced, t, copy_len);
        produced += copy_len;
        counter++;
    }

    return 0;
}

static size_t build_info_suite(const rca_ctx_t *ctx, uint8_t *out) {
    static const char prefix[] = "RCA|ctx|v2";
    size_t off = 0;

    memcpy(out + off, prefix, sizeof(prefix) - 1);
    off += sizeof(prefix) - 1;

    store_le32(out + off, ctx->alto);
    off += 4;
    store_le32(out + off, ctx->ancho);
    off += 4;
    store_le16(out + off, ctx->canales);
    off += 2;
    store_le16(out + off, ctx->rondas);
    off += 2;

    return off;
}

static int hkdf_expand_labelled(
    const uint8_t prk[32],
    const char *label,
    const rca_ctx_t *ctx,
    uint8_t out_key[32]
) {
    uint8_t info[INFO_SUITE_MAX];
    size_t info_len = 0;
    size_t label_len = strlen(label);

    if (label_len > INFO_SUITE_MAX) {
        return -1;
    }
    memcpy(info, label, label_len);
    info_len += label_len;
    info_len += build_info_suite(ctx, info + info_len);

    return hkdf_expand_sha256(prk, info, info_len, out_key, 32);
}

static int hkdf_expand_round(
    const uint8_t prk[32],
    const char *label_round,
    uint32_t round_idx,
    const rca_ctx_t *ctx,
    uint8_t out_key[32]
) {
    uint8_t info[INFO_SUITE_MAX];
    size_t label_len = strlen(label_round);
    size_t suite_len;

    if (label_len + 4 > INFO_SUITE_MAX) {
        return -1;
    }

    memcpy(info, label_round, label_len);
    store_le32(info + label_len, round_idx);
    suite_len = build_info_suite(ctx, info + label_len + 4);

    return hkdf_expand_sha256(prk, info, label_len + 4 + suite_len, out_key, 32);
}

int llaves_generar_salt(uint8_t salt[SALT_RECOMENDADO_BYTES], size_t *salt_len) {
    if (!salt || !salt_len) {
        return -1;
    }
    if (random_bytes(salt, SALT_RECOMENDADO_BYTES) != 0) {
        return -2;
    }
    *salt_len = SALT_RECOMENDADO_BYTES;
    return 0;
}

int llaves_derivar_sesion(
    const uint8_t z[32],
    const uint8_t *salt, size_t salt_len,
    const rca_ctx_t *ctx,
    llave_sesion_t *ses
) {
    if (!z || !ctx || !ses) {
        return -1;
    }

    memset(ses, 0, sizeof(*ses));
    memcpy(ses->z, z, 32);

    if (salt && salt_len > 0) {
        if (salt_len > sizeof(ses->salt)) {
            return -2;
        }
        memcpy(ses->salt, salt, salt_len);
        ses->salt_len = salt_len;
    }

    if (hkdf_extract_sha256(salt, salt_len, z, 32, ses->prk) != 0) {
        return -3;
    }
    if (hkdf_expand_labelled(ses->prk, "RCA|perm|v2", ctx, ses->kperm_base) != 0) {
        return -4;
    }
    if (hkdf_expand_labelled(ses->prk, "RCA|kernel|v2", ctx, ses->kkern_base) != 0) {
        return -5;
    }
    if (hkdf_expand_labelled(ses->prk, "RCA|mac|v2", ctx, ses->kmac) != 0) {
        return -6;
    }
    if (hkdf_expand_labelled(ses->prk, "RCA|drbg|v2", ctx, ses->kseed) != 0) {
        return -7;
    }

    return 0;
}

static int calcular_indice_permutacion(const uint8_t kperm[32], uint8_t *idx_out) {
    uint8_t digest[32];
    if (sha256_bytes(kperm, 32, digest) != 0) {
        return -1;
    }
    *idx_out = (uint8_t)(digest[0] & 0x7Fu); /* mod 128 */
    return 0;
}

static int derivar_coeficientes_moore_set(
    const uint8_t kkern[32],
    uint8_t domain_tag,
    uint16_t coef_out[8]
) {
    uint8_t material[33];
    uint8_t digest[32];
    int i;

    memcpy(material, kkern, 32);
    material[32] = domain_tag;

    if (sha256_bytes(material, sizeof(material), digest) != 0) {
        return -1;
    }

    for (i = 0; i < 8; ++i) {
        uint16_t w = load_le16(&digest[i * 2]);
        coef_out[i] = (uint16_t)((w % (RCA_P - 1u)) + 1u);
    }
    return 0;
}

int llaves_derivar_ronda(
    const llave_sesion_t *ses,
    const rca_ctx_t *ctx,
    uint32_t round_idx,
    llave_ronda_t *out
) {
    if (!ses || !ctx || !out) {
        return -1;
    }

    memset(out, 0, sizeof(*out));

    if (hkdf_expand_round(ses->prk, "RCA|perm|v2|round=", round_idx, ctx, out->kperm) != 0) {
        return -2;
    }
    if (hkdf_expand_round(ses->prk, "RCA|kernel|v2|round=", round_idx, ctx, out->kkern) != 0) {
        return -3;
    }
    if (calcular_indice_permutacion(out->kperm, &out->perm_index) != 0) {
        return -4;
    }
    if (derivar_coeficientes_moore_set(out->kkern, 0x01u, out->coef_moore_1) != 0) {
        return -5;
    }
    if (derivar_coeficientes_moore_set(out->kkern, 0x02u, out->coef_moore_2) != 0) {
        return -5;
    }

    return 0;
}

int llaves_derivar_nonce96_drbg(const rca_ctx_t *ctx, uint8_t nonce96[12]) {
    uint8_t material[32];
    uint8_t digest[32];
    static const char prefix[] = "RCA_drbg|";
    size_t off = 0;

    if (!ctx || !nonce96) {
        return -1;
    }

    memcpy(material + off, prefix, sizeof(prefix) - 1);
    off += sizeof(prefix) - 1;
    store_le32(material + off, ctx->alto);
    off += 4;
    store_le32(material + off, ctx->ancho);
    off += 4;
    store_le16(material + off, ctx->canales);
    off += 2;
    store_le16(material + off, ctx->rondas);
    off += 2;

    if (sha256_bytes(material, off, digest) != 0) {
        return -2;
    }
    memcpy(nonce96, digest, 12);
    return 0;
}

#ifdef LLAVES_DEMO
int main(void) {
    x25519_keypair_t emisor, receptor;
    uint8_t z_a[32], z_b[32];
    uint8_t salt[SALT_RECOMENDADO_BYTES];
    size_t salt_len = 0;
    uint8_t nonce96[12];
    llave_sesion_t ses;
    llave_ronda_t ronda0;
    rca_ctx_t ctx = { .alto = 512, .ancho = 512, .canales = 3, .rondas = 10 };
    int rc;
    int i;

    rc = x25519_generar_par(&emisor);
    if (rc != 0) {
        fprintf(stderr, "Error x25519_generar_par(emisor): %d\n", rc);
        return 1;
    }
    rc = x25519_generar_par(&receptor);
    if (rc != 0) {
        fprintf(stderr, "Error x25519_generar_par(receptor): %d\n", rc);
        return 1;
    }

    rc = x25519_calcular_secreto_compartido(emisor.sk, receptor.pk, z_a);
    if (rc != 0) {
        fprintf(stderr, "Error secreto compartido A: %d\n", rc);
        return 1;
    }
    rc = x25519_calcular_secreto_compartido(receptor.sk, emisor.pk, z_b);
    if (rc != 0) {
        fprintf(stderr, "Error secreto compartido B: %d\n", rc);
        return 1;
    }
    if (memcmp(z_a, z_b, 32) != 0) {
        fprintf(stderr, "Error: ZA != ZB\n");
        return 1;
    }
    if (memcmp(z_a, (uint8_t[32]){0}, 32) == 0) {
        fprintf(stderr, "Error: Z == 0^32 (abortar)\n");
        return 1;
    }

    rc = llaves_generar_salt(salt, &salt_len);
    if (rc != 0) {
        fprintf(stderr, "Error generando salt: %d\n", rc);
        return 1;
    }
    rc = llaves_derivar_sesion(z_a, salt, salt_len, &ctx, &ses);
    if (rc != 0) {
        fprintf(stderr, "Error derivando sesion: %d\n", rc);
        return 1;
    }
    rc = llaves_derivar_ronda(&ses, &ctx, 0u, &ronda0);
    if (rc != 0) {
        fprintf(stderr, "Error derivando ronda 0: %d\n", rc);
        return 1;
    }
    rc = llaves_derivar_nonce96_drbg(&ctx, nonce96);
    if (rc != 0) {
        fprintf(stderr, "Error derivando nonce96: %d\n", rc);
        return 1;
    }

    print_hex("pk_emisor", emisor.pk, 32);
    print_hex("pk_receptor", receptor.pk, 32);
    print_hex("Z", z_a, 32);
    print_hex("salt", salt, salt_len);
    print_hex("PRK", ses.prk, 32);
    print_hex("Kmac", ses.kmac, 32);
    print_hex("Kseed", ses.kseed, 32);
    print_hex("Kperm_0", ronda0.kperm, 32);
    print_hex("Kkern_0", ronda0.kkern, 32);
    print_hex("nonce96_drbg", nonce96, 12);
    printf("idx_perm(0): %u\n", (unsigned)ronda0.perm_index);
    printf("coef_moore_1(0):");
    for (i = 0; i < 8; ++i) {
        printf(" %u", (unsigned)ronda0.coef_moore_1[i]);
    }
    printf("\n");
    printf("coef_moore_2(0):");
    for (i = 0; i < 8; ++i) {
        printf(" %u", (unsigned)ronda0.coef_moore_2[i]);
    }
    printf("\n");

    return 0;
}
#endif
