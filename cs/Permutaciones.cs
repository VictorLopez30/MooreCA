using System;

namespace TTCrypto;

public static class Permutations
{
    public const int CatalogSize = 128;

    private enum Op { R, L, U, D }

    public readonly record struct PermSpec(PermRowsDir RowsDir, PermColsDir ColsDir, byte NRows, byte NCols, PermOrder Order);
    public enum PermOrder { RowsThenCols = 0, ColsThenRows = 1 }
    public enum PermRowsDir { Left = 0, Right = 1 }
    public enum PermColsDir { Up = 0, Down = 1 }

    private static readonly (Op Op1, Op Op2)[] Pairs =
    {
        (Op.R, Op.D), (Op.R, Op.U), (Op.L, Op.D), (Op.L, Op.U),
        (Op.U, Op.R), (Op.U, Op.L), (Op.D, Op.R), (Op.D, Op.L)
    };

    public static PermSpec Decode(byte permIdx)
    {
        if (permIdx >= CatalogSize) throw new ArgumentOutOfRangeException(nameof(permIdx));
        var pair = Pairs[permIdx >> 4];
        var nRows = (byte)(permIdx & 0x03);
        var nCols = (byte)((permIdx >> 2) & 0x03);
        return pair.Op1 switch
        {
            Op.R or Op.L => new PermSpec(
                pair.Op1 == Op.R ? PermRowsDir.Right : PermRowsDir.Left,
                pair.Op2 == Op.D ? PermColsDir.Down : PermColsDir.Up,
                nRows, nCols, PermOrder.RowsThenCols),
            _ => new PermSpec(
                pair.Op2 == Op.R ? PermRowsDir.Right : PermRowsDir.Left,
                pair.Op1 == Op.D ? PermColsDir.Down : PermColsDir.Up,
                nRows, nCols, PermOrder.ColsThenRows)
        };
    }

    public static void ApplyU16(ushort[] data, uint height, uint width, ushort channels, byte permIdx)
    {
        ApplySpecU16(data, height, width, channels, Decode(permIdx));
    }

    public static void ApplySpecU16(ushort[] data, uint height, uint width, ushort channels, PermSpec spec)
    {
        var (op1, n1, op2, n2) = SpecToOps(spec);
        ApplyOpU16(data, height, width, channels, op1, n1);
        ApplyOpU16(data, height, width, channels, op2, n2);
    }

    private static (Op op1, byte n1, Op op2, byte n2) SpecToOps(PermSpec spec)
    {
        if (spec.Order == PermOrder.RowsThenCols)
        {
            return (spec.RowsDir == PermRowsDir.Right ? Op.R : Op.L, spec.NRows,
                    spec.ColsDir == PermColsDir.Down ? Op.D : Op.U, spec.NCols);
        }
        return (spec.ColsDir == PermColsDir.Down ? Op.D : Op.U, spec.NCols,
                spec.RowsDir == PermRowsDir.Right ? Op.R : Op.L, spec.NRows);
    }

    private static void ApplyOpU16(ushort[] data, uint height, uint width, ushort channels, Op op, byte n)
    {
        var tmp = new ushort[data.Length];
        for (uint i = 0; i < height; i++)
        {
            for (uint j = 0; j < width; j++)
            {
                uint srcI = i, srcJ = j, dstI = i, dstJ = j;
                switch (op)
                {
                    case Op.R: srcJ = (uint)((j + i + n) % width); break;
                    case Op.L: dstJ = (uint)((j + i + n) % width); break;
                    case Op.U: srcI = (uint)((i + j + n) % height); break;
                    case Op.D: dstI = (uint)((i + j + n) % height); break;
                }
                var srcBase = ((int)srcI * (int)width + (int)srcJ) * channels;
                var dstBase = ((int)dstI * (int)width + (int)dstJ) * channels;
                Array.Copy(data, srcBase, tmp, dstBase, channels);
            }
        }
        Array.Copy(tmp, data, data.Length);
    }
}
