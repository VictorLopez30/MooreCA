using System;
using System.IO;
using TTCrypto;

internal static class Descifrado
{
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length != 9)
            {
                Console.Error.WriteLine("Uso: Descifrado <x_r-1_u16.bin> <x_r_u16.bin> <out.png|bmp|tif|tiff|raw> <ancho> <alto> <canales> <rondas> <Z_hex_64> <salt_hex_64>");
                return 1;
            }

            string prevPath = args[0];
            string curPath = args[1];
            string outPath = args[2];
            uint width = uint.Parse(args[3]);
            uint height = uint.Parse(args[4]);
            ushort channels = ushort.Parse(args[5]);
            ushort rounds = ushort.Parse(args[6]);
            byte[] z = HexUtil.FromHex(args[7]);
            byte[] salt = HexUtil.FromHex(args[8]);

            var prev = ReadU16(prevPath);
            var cur = ReadU16(curPath);
            var elems = checked((int)(width * height * channels));
            if (prev.Length != elems || cur.Length != elems)
                throw new InvalidDataException("Tamano invalido de los archivos cifrados.");

            var ctx = new RcaContext(height, width, channels, rounds);
            var session = Keys.DeriveSession(z, salt, ctx);

            var nextState = cur;
            var curState = prev;
            var curPerm = new ushort[elems];
            var prevRec = new ushort[elems];

            for (int t = rounds - 1; t >= 0; t--)
            {
                var rk = Keys.DeriveRound(session, ctx, (uint)t);
                Array.Copy(curState, curPerm, elems);
                Permutations.ApplyU16(curPerm, height, width, channels, rk.PermIndex);
                var k1 = Automata.KernelFromMoore8(rk.Moore1);
                var k2 = Automata.KernelFromMoore8(rk.Moore2);
                Automata.StepU16(nextState, curPerm, prevRec, height, width, channels, k1, k2, (uint)t, BoundaryHelper.FromRound(rk));
                (nextState, curState, prevRec) = (curState, prevRec, nextState);
            }

            var output = new byte[elems];
            for (var i = 0; i < elems; i++)
            {
                var v = nextState[i];
                output[i] = v == 0 ? (byte)255 : (byte)(v - 1);
            }

            ImageUtil.SavePreview(output, width, height, channels, outPath);
            Console.WriteLine("Descifrado completado.");
            Console.WriteLine($"Entrada estado previo: {prevPath}");
            Console.WriteLine($"Entrada estado final: {curPath}");
            Console.WriteLine($"Salida imagen: {outPath}");
            Console.WriteLine($"Dimensiones: {width}x{height} x {channels}, rondas={rounds}");
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.Message);
            return 2;
        }
    }

    private static ushort[] ReadU16(string path)
    {
        var bytes = File.ReadAllBytes(path);
        if ((bytes.Length & 1) != 0) throw new InvalidDataException("Archivo u16 invalido.");
        var data = new ushort[bytes.Length / 2];
        Buffer.BlockCopy(bytes, 0, data, 0, bytes.Length);
        return data;
    }
}
