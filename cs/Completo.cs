using System;
using System.IO;
using TTCrypto;

internal static class Completo
{
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length != 5 && args.Length != 7)
            {
                Console.Error.WriteLine("Uso auto PNG/BMP/TIFF: Completo <in.png|in.bmp|in.tif|in.tiff> <out_cipher_u16.bin> <out_preview.png|bmp|tif|tiff|raw> <out_recovered.png|bmp|tif|tiff|raw> <rondas>");
                Console.Error.WriteLine("Uso auto compartido: Completo <in.png|in.bmp|in.tif|in.tiff> <out_cipher_u16.bin> <out_preview.png|bmp|tif|tiff|raw> <out_recovered.png|bmp|tif|tiff|raw> <rondas> <Z_hex_64> <salt_hex_64>");
                return 1;
            }

            string inputPath = args[0];
            string outCipher = args[1];
            string outPreview = args[2];
            string outRecovered = args[3];
            ushort rounds = ushort.Parse(args[4]);
            byte[]? z = null;
            byte[]? salt = null;

            if (args.Length == 7)
            {
                z = HexUtil.FromHex(args[5]);
                salt = HexUtil.FromHex(args[6]);
            }

            var input = ImageUtil.LoadImageOrRaw(inputPath);
            var ctx = new RcaContext(input.Height, input.Width, input.Channels, rounds);

            if (z is null || salt is null)
            {
                var (privA, pubA) = Keys.GenerateX25519Pair();
                var (privB, pubB) = Keys.GenerateX25519Pair();
                var zA = Keys.SharedSecretFromPkcs8(privA, pubB);
                var zB = Keys.SharedSecretFromPkcs8(privB, pubA);
                if (!zA.AsSpan().SequenceEqual(zB))
                    throw new InvalidOperationException("No se pudo acordar el secreto compartido.");
                z = zA;
                salt = Keys.GenerateSalt();
            }

            var session = Keys.DeriveSession(z, salt, ctx);

            var elems = input.Raw.Length;
            var prev = new ushort[elems];
            var cur = new ushort[elems];
            var curPerm = new ushort[elems];
            var next = new ushort[elems];

            for (var i = 0; i < elems; i++)
                cur[i] = (ushort)((input.Raw[i] + 1) % CryptoConsts.AutomataModBase);

            for (uint round = 0; round < rounds; round++)
            {
                var rk = Keys.DeriveRound(session, ctx, round);
                Array.Copy(cur, curPerm, elems);
                Permutations.ApplyU16(curPerm, input.Height, input.Width, input.Channels, rk.PermIndex);
                var kernelsByChannel = new int[6][,];
                for (var ch = 0; ch < 3; ch++)
                    for (var k = 0; k < 2; k++)
                        kernelsByChannel[ch * 2 + k] = Automata.KernelFromMoore8(rk.MooreByChannel[ch][k]);
                Automata.StepU16(prev, curPerm, next, input.Height, input.Width, input.Channels, kernelsByChannel, round, BoundaryHelper.FromRound(rk));
                (prev, cur, next) = (cur, next, prev);
            }

            WriteU16(outCipher, cur);
            var prevPath = outCipher + ".prev.bin";
            WriteU16(prevPath, prev);

            var preview = new byte[cur.Length];
            for (var i = 0; i < cur.Length; i++)
                preview[i] = (byte)Math.Min(cur[i], (ushort)255);
            ImageUtil.SavePreview(preview, input.Width, input.Height, input.Channels, outPreview);

            var sessionFile = new SessionFile
            {
                Width = input.Width.ToString(),
                Height = input.Height.ToString(),
                Channels = input.Channels.ToString(),
                Rounds = rounds.ToString(),
                PrevPath = prevPath,
                CurPath = outCipher,
                ZHex = HexUtil.ToHex(z),
                SaltHex = HexUtil.ToHex(salt)
            };
            sessionFile.Save(outCipher + ".session.txt");

            var nextState = cur;
            var curState = prev;
            var curPermDec = new ushort[elems];
            var prevRec = new ushort[elems];

            for (int t = rounds - 1; t >= 0; t--)
            {
                var rk = Keys.DeriveRound(session, ctx, (uint)t);
                Array.Copy(curState, curPermDec, elems);
                Permutations.ApplyU16(curPermDec, input.Height, input.Width, input.Channels, rk.PermIndex);
                var kernelsByChannel = new int[6][,];
                for (var ch = 0; ch < 3; ch++)
                    for (var k = 0; k < 2; k++)
                        kernelsByChannel[ch * 2 + k] = Automata.KernelFromMoore8(rk.MooreByChannel[ch][k]);
                Automata.StepU16(nextState, curPermDec, prevRec, input.Height, input.Width, input.Channels, kernelsByChannel, (uint)t, BoundaryHelper.FromRound(rk));
                (nextState, curState, prevRec) = (curState, prevRec, nextState);
            }

            var output = new byte[elems];
            for (var i = 0; i < elems; i++)
            {
                var v = nextState[i];
                output[i] = v == 0 ? (byte)255 : (byte)(v - 1);
            }

            ImageUtil.SavePreview(output, input.Width, input.Height, input.Channels, outRecovered);

            Console.WriteLine("Cifrado y descifrado completados.");
            Console.WriteLine($"Entrada: {inputPath}");
            Console.WriteLine($"Salida estado mod257 (u16): {outCipher}");
            Console.WriteLine($"Salida estado previo (u16): {prevPath}");
            Console.WriteLine($"Archivo de sesion: {outCipher}.session.txt");
            Console.WriteLine($"Salida preview recortada (u8): {outPreview}");
            Console.WriteLine($"Salida recuperada: {outRecovered}");
            Console.WriteLine($"Dimensiones: {input.Width}x{input.Height} x {input.Channels}, rondas={rounds}");
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.Message);
            return 2;
        }
    }

    private static void WriteU16(string path, ushort[] data)
    {
        using var bw = new BinaryWriter(File.Create(path));
        foreach (var v in data) bw.Write(v);
    }
}
