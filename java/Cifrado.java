import java.nio.file.Path;
import java.util.HexFormat;

public final class Cifrado {
    public static void main(String[] args) throws Exception {
        if (args.length != 4 && args.length != 7 && args.length != 6 && args.length != 9) {
            System.err.println("Uso auto PNG/BMP/TIFF: java Cifrado <in.png|in.bmp|in.tif|in.tiff> <out_cipher_u16.bin> <out_preview.png|bmp|tif|tiff|raw> <rondas>");
            System.err.println("Uso auto compartido: java Cifrado <in.png|in.bmp|in.tif|in.tiff> <out_cipher_u16.bin> <out_preview.png|bmp|tif|tiff|raw> <rondas> <Z_hex_64> <salt_hex_64>");
            System.err.println("Uso RAW: java Cifrado <in.raw> <out_cipher_u16.bin> <out_preview.raw|png|bmp|tif|tiff> <ancho> <alto> <canales> <rondas>");
            System.err.println("Uso RAW compartido: java Cifrado <in.raw> <out_cipher_u16.bin> <out_preview.raw|png|bmp|tif|tiff> <ancho> <alto> <canales> <rondas> <Z_hex_64> <salt_hex_64>");
            System.exit(1);
        }

        String inputPath = args[0];
        String outCipher = args[1];
        String outPreview = args[2];
        int rounds;
        Integer width = null, height = null, channels = null;
        byte[] z = null;
        byte[] salt = null;

        if (args.length == 4 || args.length == 6) {
            rounds = Integer.parseInt(args[3]);
            if (args.length == 6) {
                z = HexFormat.of().parseHex(args[4]);
                salt = HexFormat.of().parseHex(args[5]);
            }
        } else {
            width = Integer.parseInt(args[3]);
            height = Integer.parseInt(args[4]);
            channels = Integer.parseInt(args[5]);
            rounds = Integer.parseInt(args[6]);
            if (args.length == 9) {
                z = HexFormat.of().parseHex(args[7]);
                salt = HexFormat.of().parseHex(args[8]);
            }
        }

        Common.LoadedImage input = Common.loadImageOrRaw(inputPath, width, height, channels);
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

        System.out.println("Cifrado completado.");
        System.out.println("Entrada: " + inputPath);
        System.out.println("Salida estado mod257 (u16): " + outCipher);
        System.out.println("Salida estado previo (u16): " + prevPath);
        System.out.println("Archivo de sesion: " + outCipher + ".session.txt");
        System.out.println("Salida preview recortada (u8): " + outPreview);
        System.out.printf("Dimensiones: %dx%d x %d, rondas=%d%n", input.width(), input.height(), input.channels(), rounds);
    }
}
