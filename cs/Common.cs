using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;

namespace TTCrypto;

public static class CryptoConsts
{
    public const int AutomataModBase = 257;
    public const int KeyBytes = 32;
    public const int SaltBytes = 32;
}

public enum BoundaryMode
{
    Periodic = 0,
    Reflect = 1,
    Adiabatic = 2
}

public readonly record struct BoundaryConfig(
    BoundaryMode Top,
    BoundaryMode Bottom,
    BoundaryMode Left,
    BoundaryMode Right
);

public readonly record struct RcaContext(uint Height, uint Width, ushort Channels, ushort Rounds);

public sealed class SessionFile
{
    public string Width { get; set; } = "";
    public string Height { get; set; } = "";
    public string Channels { get; set; } = "";
    public string Rounds { get; set; } = "";
    public string PrevPath { get; set; } = "";
    public string CurPath { get; set; } = "";
    public string ZHex { get; set; } = "";
    public string SaltHex { get; set; } = "";

    public static SessionFile Parse(string path)
    {
        var data = new SessionFile();
        foreach (var raw in File.ReadAllLines(path))
        {
            var line = raw.Trim();
            if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal)) continue;
            var idx = line.IndexOf('=');
            if (idx <= 0) continue;
            var key = line[..idx];
            var value = line[(idx + 1)..];
            switch (key)
            {
                case "ancho": data.Width = value; break;
                case "alto": data.Height = value; break;
                case "canales": data.Channels = value; break;
                case "rondas": data.Rounds = value; break;
                case "x_prev_path": data.PrevPath = value; break;
                case "x_cur_path": data.CurPath = value; break;
                case "z_hex": data.ZHex = value; break;
                case "salt_hex": data.SaltHex = value; break;
            }
        }

        if (string.IsNullOrWhiteSpace(data.Width) || string.IsNullOrWhiteSpace(data.Height) ||
            string.IsNullOrWhiteSpace(data.Channels) || string.IsNullOrWhiteSpace(data.Rounds) ||
            string.IsNullOrWhiteSpace(data.PrevPath) || string.IsNullOrWhiteSpace(data.CurPath) ||
            string.IsNullOrWhiteSpace(data.ZHex) || string.IsNullOrWhiteSpace(data.SaltHex))
        {
            throw new InvalidDataException("Archivo de sesion incompleto.");
        }

        return data;
    }

    public void Save(string path)
    {
        var sb = new StringBuilder();
        sb.AppendLine("# Sesion de cifrado");
        sb.AppendLine($"ancho={Width}");
        sb.AppendLine($"alto={Height}");
        sb.AppendLine($"canales={Channels}");
        sb.AppendLine($"rondas={Rounds}");
        sb.AppendLine($"x_prev_path={PrevPath}");
        sb.AppendLine($"x_cur_path={CurPath}");
        sb.AppendLine($"z_hex={ZHex}");
        sb.AppendLine($"salt_hex={SaltHex}");
        File.WriteAllText(path, sb.ToString());
    }
}

public static class HexUtil
{
    public static string ToHex(byte[] data) => Convert.ToHexString(data).ToLowerInvariant();
    public static byte[] FromHex(string hex) => Convert.FromHexString(hex);
}

public static class ImageUtil
{
    public static (byte[] Raw, uint Width, uint Height, ushort Channels) LoadImageOrRaw(
        string path,
        uint width = 0,
        uint height = 0,
        ushort channels = 0)
    {
        var ext = Path.GetExtension(path).ToLowerInvariant();
        if (ext == ".png" || ext == ".bmp")
        {
            var tmp = Path.GetTempFileName();
            try
            {
                RunProcess("ffmpeg", $"-y -v error -i \"{path}\" -f rawvideo -pix_fmt rgb24 \"{tmp}\"");
                var (w, h) = ProbeDimensions(path);
                return (File.ReadAllBytes(tmp), w, h, 3);
            }
            finally
            {
                if (File.Exists(tmp)) File.Delete(tmp);
            }
        }

        if (width == 0 || height == 0 || channels == 0)
            throw new ArgumentException("Para .raw debes proporcionar ancho, alto y canales.");

        return (File.ReadAllBytes(path), width, height, channels);
    }

    public static void SavePreview(byte[] raw, uint width, uint height, ushort channels, string path)
    {
        var ext = Path.GetExtension(path).ToLowerInvariant();
        if ((ext == ".png" || ext == ".bmp") && channels == 3)
        {
            var tmp = Path.GetTempFileName();
            try
            {
                File.WriteAllBytes(tmp, raw);
                RunProcess("ffmpeg", $"-y -v error -f rawvideo -pix_fmt rgb24 -s {width}x{height} -i \"{tmp}\" \"{path}\"");
                return;
            }
            finally
            {
                if (File.Exists(tmp)) File.Delete(tmp);
            }
        }

        File.WriteAllBytes(path, raw);
    }

    public static (uint Width, uint Height) ProbeDimensions(string path)
    {
        var output = RunProcessCapture("ffprobe", $"-v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x \"{path}\"");
        var parts = output.Trim().Split('x');
        if (parts.Length != 2) throw new InvalidDataException("No se pudieron obtener dimensiones.");
        return (uint.Parse(parts[0], CultureInfo.InvariantCulture), uint.Parse(parts[1], CultureInfo.InvariantCulture));
    }

    public static string RunProcessCapture(string fileName, string args)
    {
        using var p = new Process();
        p.StartInfo.FileName = fileName;
        p.StartInfo.Arguments = args;
        p.StartInfo.RedirectStandardOutput = true;
        p.StartInfo.RedirectStandardError = true;
        p.StartInfo.UseShellExecute = false;
        p.StartInfo.CreateNoWindow = true;
        p.Start();
        var stdout = p.StandardOutput.ReadToEnd();
        var stderr = p.StandardError.ReadToEnd();
        p.WaitForExit();
        if (p.ExitCode != 0) throw new InvalidOperationException($"{fileName} fallo: {stderr}");
        return stdout;
    }

    public static void RunProcess(string fileName, string args)
    {
        RunProcessCapture(fileName, args);
    }
}

public static class BoundaryHelper
{
    public static BoundaryConfig FromRound(RoundKeys round) => new(
        Map(round.KKernel[0]), Map(round.KKernel[1]), Map(round.KKernel[2]), Map(round.KKernel[3]));

    private static BoundaryMode Map(byte b) => (BoundaryMode)(b % 3);
}
