namespace TTCrypto;

public static class Automata
{
    public static int[,] KernelFromMoore8(ushort[] coeffs)
    {
        return new[,]
        {
            { coeffs[0], coeffs[1], coeffs[2] },
            { coeffs[7], 0, coeffs[3] },
            { coeffs[6], coeffs[5], coeffs[4] }
        };
    }

    public static void StepU16(
        ushort[] prevState,
        ushort[] curPermuted,
        ushort[] nextState,
        uint height,
        uint width,
        ushort channels,
        int[][,] kernelsByChannel,
        uint roundIndex,
        BoundaryConfig bc)
    {
        for (uint y = 0; y < height; y++)
        {
            for (uint x = 0; x < width; x++)
            {
                for (ushort c = 0; c < channels; c++)
                {
                    long acc = 0;
                    var kernel = SelectKernel(y, x, c, roundIndex, kernelsByChannel);
                    for (var dy = -1; dy <= 1; dy++)
                    {
                        for (var dx = -1; dx <= 1; dx++)
                        {
                            var ny = MapY((int)y + dy, (int)height, bc);
                            var nx = MapX((int)x + dx, (int)width, bc);
                            var idx = Index3((uint)ny, (uint)nx, c, width, channels);
                            acc += (long)kernel[dy + 1, dx + 1] * curPermuted[idx];
                        }
                    }
                    var pos = Index3(y, x, c, width, channels);
                    var conv = Mod257(acc);
                    nextState[pos] = (ushort)Mod257(conv - prevState[pos]);
                }
            }
        }
    }

    private static int[,] SelectKernel(uint y, uint x, ushort c, uint roundIndex, int[][,] kernelsByChannel)
        => kernelsByChannel[(c % 3) * 2 + ((((y + x + c + roundIndex) & 1u) == 0u) ? 0 : 1)];

    private static int Index3(uint y, uint x, ushort c, uint width, ushort channels)
        => ((int)y * (int)width + (int)x) * channels + c;

    private static int Mod257(long x)
    {
        var r = x % CryptoConsts.AutomataModBase;
        if (r < 0) r += CryptoConsts.AutomataModBase;
        return (int)r;
    }

    private static int Clamp(int idx, int max) => idx < 0 ? 0 : (idx >= max ? max - 1 : idx);

    private static int Wrap(int idx, int max)
    {
        var r = idx % max;
        return r < 0 ? r + max : r;
    }

    private static int MapY(int y, int h, BoundaryConfig bc)
        => y >= 0 && y < h ? y : (y < 0 ? (bc.Top == BoundaryMode.Periodic ? Wrap(y, h) : Clamp(y, h))
                                        : (bc.Bottom == BoundaryMode.Periodic ? Wrap(y, h) : Clamp(y, h)));

    private static int MapX(int x, int w, BoundaryConfig bc)
        => x >= 0 && x < w ? x : (x < 0 ? (bc.Left == BoundaryMode.Periodic ? Wrap(x, w) : Clamp(x, w))
                                        : (bc.Right == BoundaryMode.Periodic ? Wrap(x, w) : Clamp(x, w)));
}
