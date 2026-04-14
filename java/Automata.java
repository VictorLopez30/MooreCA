final class Automata {
    static int[][] kernelFromMoore8(int[] coeffs) {
        return new int[][] {
            { coeffs[0], coeffs[1], coeffs[2] },
            { coeffs[7], 0, coeffs[3] },
            { coeffs[6], coeffs[5], coeffs[4] }
        };
    }

    static void stepU16(
        short[] prev,
        short[] curPerm,
        short[] next,
        int height,
        int width,
        int channels,
        int[][] k1,
        int[][] k2,
        int round,
        Common.BoundaryConfig bc
    ) {
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                for (int c = 0; c < channels; c++) {
                    long acc = 0;
                    int[][] k = (((y + x + c + round) & 1) == 0) ? k1 : k2;
                    for (int dy = -1; dy <= 1; dy++) {
                        for (int dx = -1; dx <= 1; dx++) {
                            int ny = mapY(y + dy, height, bc);
                            int nx = mapX(x + dx, width, bc);
                            int idx = ((ny * width) + nx) * channels + c;
                            acc += (long)k[dy + 1][dx + 1] * Short.toUnsignedInt(curPerm[idx]);
                        }
                    }
                    int pos = ((y * width) + x) * channels + c;
                    int conv = mod257(acc);
                    next[pos] = (short)mod257(conv - Short.toUnsignedInt(prev[pos]));
                }
            }
        }
    }

    private static int mod257(long x) {
        long r = x % Common.AUTOMATA_MOD_BASE;
        return (int)(r < 0 ? r + Common.AUTOMATA_MOD_BASE : r);
    }

    private static int clamp(int idx, int max) {
        return idx < 0 ? 0 : (idx >= max ? max - 1 : idx);
    }

    private static int wrap(int idx, int max) {
        int r = idx % max;
        return r < 0 ? r + max : r;
    }

    private static int mapY(int y, int h, Common.BoundaryConfig bc) {
        if (y >= 0 && y < h) return y;
        if (y < 0) return bc.top() == Common.BoundaryMode.PERIODIC ? wrap(y, h) : clamp(y, h);
        return bc.bottom() == Common.BoundaryMode.PERIODIC ? wrap(y, h) : clamp(y, h);
    }

    private static int mapX(int x, int w, Common.BoundaryConfig bc) {
        if (x >= 0 && x < w) return x;
        if (x < 0) return bc.left() == Common.BoundaryMode.PERIODIC ? wrap(x, w) : clamp(x, w);
        return bc.right() == Common.BoundaryMode.PERIODIC ? wrap(x, w) : clamp(x, w);
    }
}
