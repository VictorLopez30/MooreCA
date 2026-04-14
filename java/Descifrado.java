import java.nio.file.Path;
import java.util.HexFormat;

public final class Descifrado {
    public static void main(String[] args) throws Exception {
        if (args.length != 9) {
            System.err.println("Uso: java Descifrado <x_r-1_u16.bin> <x_r_u16.bin> <out.png|bmp|raw> <ancho> <alto> <canales> <rondas> <Z_hex_64> <salt_hex_64>");
            System.exit(1);
        }

        String prevPath = args[0];
        String curPath = args[1];
        String outPath = args[2];
        int width = Integer.parseInt(args[3]);
        int height = Integer.parseInt(args[4]);
        int channels = Integer.parseInt(args[5]);
        int rounds = Integer.parseInt(args[6]);
        byte[] z = HexFormat.of().parseHex(args[7]);
        byte[] salt = HexFormat.of().parseHex(args[8]);

        short[] prev = Common.readU16(Path.of(prevPath));
        short[] cur = Common.readU16(Path.of(curPath));
        int elems = width * height * channels;
        if (prev.length != elems || cur.length != elems) {
            throw new IllegalArgumentException("Tamano invalido de archivos cifrados.");
        }

        Common.RcaContext ctx = new Common.RcaContext(height, width, channels, rounds);
        var session = Llaves.deriveSession(z, salt, ctx);

        short[] nextState = cur;
        short[] curState = prev;
        short[] curPerm = new short[elems];
        short[] prevRec = new short[elems];

        for (int t = rounds - 1; t >= 0; t--) {
            var rk = Llaves.deriveRound(session, ctx, t);
            System.arraycopy(curState, 0, curPerm, 0, elems);
            Permutaciones.applyU16(curPerm, height, width, channels, rk.permIndex());
            int[][] k1 = Automata.kernelFromMoore8(rk.moore1());
            int[][] k2 = Automata.kernelFromMoore8(rk.moore2());
            Automata.stepU16(nextState, curPerm, prevRec, height, width, channels, k1, k2, t, Llaves.boundaryFromRound(rk));
            short[] tmp = nextState; nextState = curState; curState = prevRec; prevRec = tmp;
        }

        byte[] output = new byte[elems];
        for (int i = 0; i < elems; i++) {
            int v = Short.toUnsignedInt(nextState[i]);
            output[i] = (byte)(v == 0 ? 255 : v - 1);
        }
        Common.savePreview(output, width, height, channels, outPath);

        System.out.println("Descifrado completado.");
        System.out.println("Entrada estado previo: " + prevPath);
        System.out.println("Entrada estado final: " + curPath);
        System.out.println("Salida imagen: " + outPath);
        System.out.printf("Dimensiones: %dx%d x %d, rondas=%d%n", width, height, channels, rounds);
    }
}
