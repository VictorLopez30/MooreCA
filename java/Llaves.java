import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.spec.NamedParameterSpec;
import java.util.Arrays;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

final class Llaves {
    record SessionKeys(byte[] z, byte[] salt, byte[] prk, byte[] kPermBase, byte[] kKernelBase, byte[] kMac, byte[] kSeed) {}
    record RoundKeys(byte[] kPerm, byte[] kKernel, int permIndex, int[] moore1, int[] moore2) {}

    static byte[] generateSalt() {
        byte[] salt = new byte[Common.SALT_BYTES];
        new SecureRandom().nextBytes(salt);
        return salt;
    }

    static byte[] deriveSharedSecret() throws Exception {
        KeyPairGenerator kpg = KeyPairGenerator.getInstance("X25519");
        kpg.initialize(new NamedParameterSpec("X25519"));
        KeyPair a = kpg.generateKeyPair();
        KeyPair b = kpg.generateKeyPair();
        KeyAgreement ka = KeyAgreement.getInstance("X25519");
        ka.init(a.getPrivate());
        ka.doPhase(b.getPublic(), true);
        byte[] za = ka.generateSecret();
        KeyAgreement kb = KeyAgreement.getInstance("X25519");
        kb.init(b.getPrivate());
        kb.doPhase(a.getPublic(), true);
        byte[] zb = kb.generateSecret();
        if (!Arrays.equals(za, zb)) throw new IllegalStateException("No coinciden los secretos X25519.");
        return za;
    }

    static SessionKeys deriveSession(byte[] z, byte[] salt, Common.RcaContext ctx) throws Exception {
        byte[] prk = hkdfExtract(salt, z);
        return new SessionKeys(
            z.clone(),
            salt.clone(),
            prk,
            hkdfExpand(prk, buildInfo("RCA|perm|v2", ctx), 32),
            hkdfExpand(prk, buildInfo("RCA|kernel|v2", ctx), 32),
            hkdfExpand(prk, buildInfo("RCA|mac|v2", ctx), 32),
            hkdfExpand(prk, buildInfo("RCA|drbg|v2", ctx), 32)
        );
    }

    static RoundKeys deriveRound(SessionKeys session, Common.RcaContext ctx, int round) throws Exception {
        byte[] kPerm = hkdfExpand(session.prk(), buildRoundInfo("RCA|perm|v2|round=", round, ctx), 32);
        byte[] kKernel = hkdfExpand(session.prk(), buildRoundInfo("RCA|kernel|v2|round=", round, ctx), 32);
        byte permIndex = (byte)(MessageDigest.getInstance("SHA-256").digest(kPerm)[0] & 0x7F);
        return new RoundKeys(kPerm, kKernel, permIndex & 0xFF, deriveMoore(kKernel, (byte)1), deriveMoore(kKernel, (byte)2));
    }

    static Common.BoundaryConfig boundaryFromRound(RoundKeys rk) {
        return new Common.BoundaryConfig(
            Common.BoundaryMode.values()[(rk.kKernel()[0] & 0xFF) % 3],
            Common.BoundaryMode.values()[(rk.kKernel()[1] & 0xFF) % 3],
            Common.BoundaryMode.values()[(rk.kKernel()[2] & 0xFF) % 3],
            Common.BoundaryMode.values()[(rk.kKernel()[3] & 0xFF) % 3]
        );
    }

    private static byte[] hkdfExtract(byte[] salt, byte[] ikm) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec((salt == null || salt.length == 0) ? new byte[32] : salt, "HmacSHA256"));
        return mac.doFinal(ikm);
    }

    private static byte[] hkdfExpand(byte[] prk, byte[] info, int length) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(prk, "HmacSHA256"));
        byte[] okm = new byte[length];
        byte[] t = new byte[0];
        int off = 0;
        byte counter = 1;
        while (off < length) {
            ByteArrayOutputStream block = new ByteArrayOutputStream();
            block.write(t);
            block.write(info);
            block.write(counter++);
            t = mac.doFinal(block.toByteArray());
            int copy = Math.min(t.length, length - off);
            System.arraycopy(t, 0, okm, off, copy);
            off += copy;
        }
        return okm;
    }

    private static byte[] buildInfo(String label, Common.RcaContext ctx) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(label.getBytes(StandardCharsets.US_ASCII));
        out.write("RCA|ctx|v2".getBytes(StandardCharsets.US_ASCII));
        writeLe32(out, ctx.height());
        writeLe32(out, ctx.width());
        writeLe16(out, ctx.channels());
        writeLe16(out, ctx.rounds());
        return out.toByteArray();
    }

    private static byte[] buildRoundInfo(String label, int round, Common.RcaContext ctx) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(label.getBytes(StandardCharsets.US_ASCII));
        writeLe32(out, round);
        out.write("RCA|ctx|v2".getBytes(StandardCharsets.US_ASCII));
        writeLe32(out, ctx.height());
        writeLe32(out, ctx.width());
        writeLe16(out, ctx.channels());
        writeLe16(out, ctx.rounds());
        return out.toByteArray();
    }

    private static int[] deriveMoore(byte[] kKernel, byte tag) throws Exception {
        byte[] material = Arrays.copyOf(kKernel, 33);
        material[32] = tag;
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(material);
        int[] out = new int[8];
        for (int i = 0; i < 8; i++) {
            int w = Short.toUnsignedInt(ByteBuffer.wrap(digest, i * 2, 2).order(ByteOrder.LITTLE_ENDIAN).getShort());
            out[i] = (w % 256) + 1;
        }
        return out;
    }

    private static void writeLe16(OutputStream out, int value) throws IOException {
        out.write(value & 0xFF);
        out.write((value >>> 8) & 0xFF);
    }

    private static void writeLe32(OutputStream out, int value) throws IOException {
        out.write(value & 0xFF);
        out.write((value >>> 8) & 0xFF);
        out.write((value >>> 16) & 0xFF);
        out.write((value >>> 24) & 0xFF);
    }
}
