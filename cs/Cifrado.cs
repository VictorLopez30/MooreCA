using System;
using System.IO;
using TTCrypto;

internal static class Cifrado
{
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length != 4 && args.Length != 7 && args.Length != 6 && args.Length != 9)
            {
                Console.Error.WriteLine("Uso auto PNG/BMP/TIFF: Cifrado <in.png|in.bmp|in.tif|in.tiff> <out_cipher_u16.bin> <out_preview.png|bmp|tif|tiff|raw> <rondas>");
                Console.Error.WriteLine("Uso auto compartido: Cifrado <in.png|in.bmp|in.tif|in.tiff> <out_cipher_u16.bin> <out_preview.png|bmp|tif|tiff|raw> <rondas> <Z_hex_64> <salt_hex_64>");
                Console.Error.WriteLine("Uso RAW: Cifrado <in.raw> <out_cipher_u16.bin> <out_preview.raw|png|bmp|tif|tiff> <ancho> <alto> <canales> <rondas>");
                Console.Error.WriteLine("Uso RAW compartido: Cifrado <in.raw> <out_cipher_u16.bin> <out_preview.raw|png|bmp|tif|tiff> <ancho> <alto> <canales> <rondas> <Z_hex_64> <salt_hex_64>");
                return 1;
            }

            string inputPath = args[0];
            string outCipher = args[1];
            string outPreview = args[2];
            ushort rounds;
            uint width = 0, height = 0;
            ushort channels = 0;
            bool auto = args.Length == 4 || args.Length == 6;
            byte[]? z = null;
            byte[]? salt = null;

            if (auto)
            {
                rounds = ushort.Parse(args[3]);
                if (args.Length == 6)
                {
                    z = HexUtil.FromHex(args[4]);
                    salt = HexUtil.FromHex(args[5]);
                }
            }
            else
            {
                width = uint.Parse(args[3]);
                height = uint.Parse(args[4]);
                channels = ushort.Parse(args[5]);
                rounds = ushort.Parse(args[6]);
                if (args.Length == 9)
                {
                    z = HexUtil.FromHex(args[7]);
                    salt = HexUtil.FromHex(args[8]);
                }
            }

            var input = ImageUtil.LoadImageOrRaw(inputPath, width, height, channels);
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
                var k1 = Automata.KernelFromMoore8(rk.Moore1);
                var k2 = Automata.KernelFromMoore8(rk.Moore2);
                Automata.StepU16(prev, curPerm, next, input.Height, input.Width, input.Channels, k1, k2, round, BoundaryHelper.FromRound(rk));
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

            Console.WriteLine("Cifrado completado.");
            Console.WriteLine($"Entrada: {inputPath}");
            Console.WriteLine($"Salida estado mod257 (u16): {outCipher}");
            Console.WriteLine($"Salida estado previo (u16): {prevPath}");
            Console.WriteLine($"Archivo de sesion: {outCipher}.session.txt");
            Console.WriteLine($"Salida preview recortada (u8): {outPreview}");
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
