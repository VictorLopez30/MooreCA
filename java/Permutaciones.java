final class Permutaciones {
    static final int CATALOG_SIZE = 128;

    enum Op { R, L, U, D }
    enum PermOrder { ROWS_THEN_COLS, COLS_THEN_ROWS }
    enum PermRowsDir { LEFT, RIGHT }
    enum PermColsDir { UP, DOWN }

    record PermSpec(PermRowsDir rowsDir, PermColsDir colsDir, int nRows, int nCols, PermOrder order) {}

    static final Op[][] PAIRS = {
        {Op.R, Op.D}, {Op.R, Op.U}, {Op.L, Op.D}, {Op.L, Op.U},
        {Op.U, Op.R}, {Op.U, Op.L}, {Op.D, Op.R}, {Op.D, Op.L}
    };

    static PermSpec decode(int permIdx) {
        if (permIdx < 0 || permIdx >= CATALOG_SIZE) throw new IllegalArgumentException("permIdx invalido");
        int pairIdx = permIdx >> 4;
        int nRows = permIdx & 0x03;
        int nCols = (permIdx >> 2) & 0x03;
        Op[] pair = PAIRS[pairIdx];
        if (pair[0] == Op.R || pair[0] == Op.L) {
            return new PermSpec(
                pair[0] == Op.R ? PermRowsDir.RIGHT : PermRowsDir.LEFT,
                pair[1] == Op.D ? PermColsDir.DOWN : PermColsDir.UP,
                nRows, nCols, PermOrder.ROWS_THEN_COLS
            );
        }
        return new PermSpec(
            pair[1] == Op.R ? PermRowsDir.RIGHT : PermRowsDir.LEFT,
            pair[0] == Op.D ? PermColsDir.DOWN : PermColsDir.UP,
            nRows, nCols, PermOrder.COLS_THEN_ROWS
        );
    }

    static void applyU16(short[] data, int height, int width, int channels, int permIdx) {
        applySpecU16(data, height, width, channels, decode(permIdx));
    }

    static void applySpecU16(short[] data, int height, int width, int channels, PermSpec spec) {
        Object[] ops = specToOps(spec);
        applyOpU16(data, height, width, channels, (Op)ops[0], (Integer)ops[1]);
        applyOpU16(data, height, width, channels, (Op)ops[2], (Integer)ops[3]);
    }

    private static Object[] specToOps(PermSpec spec) {
        if (spec.order() == PermOrder.ROWS_THEN_COLS) {
            return new Object[] {
                spec.rowsDir() == PermRowsDir.RIGHT ? Op.R : Op.L, spec.nRows(),
                spec.colsDir() == PermColsDir.DOWN ? Op.D : Op.U, spec.nCols()
            };
        }
        return new Object[] {
            spec.colsDir() == PermColsDir.DOWN ? Op.D : Op.U, spec.nCols(),
            spec.rowsDir() == PermRowsDir.RIGHT ? Op.R : Op.L, spec.nRows()
        };
    }

    private static void applyOpU16(short[] data, int height, int width, int channels, Op op, int n) {
        short[] tmp = new short[data.length];
        for (int i = 0; i < height; i++) {
            for (int j = 0; j < width; j++) {
                int srcI = i;
                int srcJ = j;
                int dstI = i;
                int dstJ = j;
                switch (op) {
                    case R -> srcJ = (j + i + n) % width;
                    case L -> dstJ = (j + i + n) % width;
                    case U -> srcI = (i + j + n) % height;
                    case D -> dstI = (i + j + n) % height;
                }
                int srcBase = (srcI * width + srcJ) * channels;
                int dstBase = (dstI * width + dstJ) * channels;
                System.arraycopy(data, srcBase, tmp, dstBase, channels);
            }
        }
        System.arraycopy(tmp, 0, data, 0, data.length);
    }
}
