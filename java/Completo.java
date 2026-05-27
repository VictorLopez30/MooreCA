import java.nio.file.Path;
import java.util.HexFormat;

public final class Completo {
    public static void main(String[] args) throws Exception {
        if (args.length != 5 && args.length != 7) {
            System.err.println("Uso auto PNG/BMP/TIFF: java Completo <in.png|in.bmp|in.tif|in.tiff> <out_cipher_u16.bin> <out_preview.png|bmp|tif|tiff|raw> <out_recovered.png|bmp|tif|tiff|raw> <rondas>");
            System.err.println("Uso auto compartido: java Completo <in.png|in.bmp|in.tif|in.tiff> <out_cipher_u16.bin> <out_preview.png|bmp|tif|tiff|raw> <out_recovered.png|bmp|tif|tiff|raw> <rondas> <Z_hex_64> <salt_hex_64>");
            System.exit(1);
        }

        String inputPath = args[0];
        String outCipher = args[1];
        String outPreview = args[2];
        String outRecovered = args[3];
        int rounds = Integer.parseInt(args[4]);
        byte[] z = null;
        byte[] salt = null;
        if (args.length == 7) {
            z = HexFormat.of().parseHex(args[5]);
            salt = HexFormat.of().parseHex(args[6]);
        }

        Common.LoadedImage input = Common.loadImageOrRaw(inputPath, null, null, null);
        Common.RcaContext ctx = new Common.RcaContext(input.height(), input.width(), input.channels(), rounds);
        if (z == null || salt == null) {
            z = Llaves.deriveSharedSecret();
            salt = Llaves.generateSalt();
        }
        var session = Llaves.deriveSession(z, salt, ctx);

        int elems = input.raw().length;
        short[] prev = new short[elems];
        short[] cur = new short[elems];
        short[] curPerm = new short[elems];
        short[] next = new short[elems];

        for (int i = 0; i < elems; i++) {
            cur[i] = (short)((Byte.toUnsignedInt(input.raw()[i]) + 1) % Common.AUTOMATA_MOD_BASE);
        }

        for (int round = 0; round < rounds; round++) {
            var rk = Llaves.deriveRound(session, ctx, round);
            System.arraycopy(cur, 0, curPerm, 0, elems);
            Permutaciones.applyU16(curPerm, input.height(), input.width(), input.channels(), rk.permIndex());
            int[][][][] kernels = new int[3][2][][];
            for (int ch = 0; ch < 3; ch++) {
                for (int k = 0; k < 2; k++) {
                    kernels[ch][k] = Automata.kernelFromMoore8(rk.mooreByChannel()[ch][k]);
                }
            }
            Automata.stepU16(prev, curPerm, next, input.height(), input.width(), input.channels(), kernels, round, Llaves.boundaryFromRound(rk));
            short[] tmp = prev; prev = cur; cur = next; next = tmp;
        }

        Common.writeU16(Path.of(outCipher), cur);
        String prevPath = outCipher + ".prev.bin";
        Common.writeU16(Path.of(prevPath), prev);

        byte[] preview = new byte[cur.length];
        for (int i = 0; i < cur.length; i++) preview[i] = (byte)Math.min(Short.toUnsignedInt(cur[i]), 255);
        Common.savePreview(preview, input.width(), input.height(), input.channels(), outPreview);

        Common.SessionFile sessionFile = new Common.SessionFile();
        sessionFile.width = Integer.toString(input.width());
        sessionFile.height = Integer.toString(input.height());
        sessionFile.channels = Integer.toString(input.channels());
        sessionFile.rounds = Integer.toString(rounds);
        sessionFile.prevPath = prevPath;
        sessionFile.curPath = outCipher;
        sessionFile.zHex = HexFormat.of().formatHex(z);
        sessionFile.saltHex = HexFormat.of().formatHex(salt);
        sessionFile.save(Path.of(outCipher + ".session.txt"));

        short[] nextState = cur;
        short[] curState = prev;
        short[] curPermDec = new short[elems];
        short[] prevRec = new short[elems];

        for (int t = rounds - 1; t >= 0; t--) {
            var rk = Llaves.deriveRound(session, ctx, t);
            System.arraycopy(curState, 0, curPermDec, 0, elems);
            Permutaciones.applyU16(curPermDec, input.height(), input.width(), input.channels(), rk.permIndex());
            int[][][][] kernels = new int[3][2][][];
            for (int ch = 0; ch < 3; ch++) {
                for (int k = 0; k < 2; k++) {
                    kernels[ch][k] = Automata.kernelFromMoore8(rk.mooreByChannel()[ch][k]);
                }
            }
            Automata.stepU16(nextState, curPermDec, prevRec, input.height(), input.width(), input.channels(), kernels, t, Llaves.boundaryFromRound(rk));
            short[] tmp = nextState; nextState = curState; curState = prevRec; prevRec = tmp;
        }

        byte[] output = new byte[elems];
        for (int i = 0; i < elems; i++) {
            int v = Short.toUnsignedInt(nextState[i]);
            output[i] = (byte)(v == 0 ? 255 : v - 1);
        }
        Common.savePreview(output, input.width(), input.height(), input.channels(), outRecovered);

        System.out.println("Cifrado y descifrado completados.");
        System.out.println("Entrada: " + inputPath);
        System.out.println("Salida estado mod257 (u16): " + outCipher);
        System.out.println("Salida estado previo (u16): " + prevPath);
        System.out.println("Archivo de sesion: " + outCipher + ".session.txt");
        System.out.println("Salida preview recortada (u8): " + outPreview);
        System.out.println("Salida recuperada: " + outRecovered);
        System.out.printf("Dimensiones: %dx%d x %d, rondas=%d%n", input.width(), input.height(), input.channels(), rounds);
    }
}
