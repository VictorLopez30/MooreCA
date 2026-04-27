using System;
using System.Buffers.Binary;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.Security;

namespace TTCrypto;

public sealed class SessionKeys
{
    public byte[] Z { get; init; } = new byte[CryptoConsts.KeyBytes];
    public byte[] Salt { get; init; } = new byte[CryptoConsts.SaltBytes];
    public byte[] Prk { get; init; } = new byte[CryptoConsts.KeyBytes];
    public byte[] KPermBase { get; init; } = new byte[CryptoConsts.KeyBytes];
    public byte[] KKernelBase { get; init; } = new byte[CryptoConsts.KeyBytes];
    public byte[] KMac { get; init; } = new byte[CryptoConsts.KeyBytes];
    public byte[] KSeed { get; init; } = new byte[CryptoConsts.KeyBytes];
}

public sealed class RoundKeys
{
    public byte[] KPerm { get; init; } = new byte[CryptoConsts.KeyBytes];
    public byte[] KKernel { get; init; } = new byte[CryptoConsts.KeyBytes];
    public byte PermIndex { get; init; }
    public ushort[][][] MooreByChannel { get; init; } =
    [
        [new ushort[8], new ushort[8]],
        [new ushort[8], new ushort[8]],
        [new ushort[8], new ushort[8]]
    ];
}

public static class Keys
{
    public static byte[] GenerateSalt()
    {
        var salt = new byte[CryptoConsts.SaltBytes];
        RandomNumberGenerator.Fill(salt);
        return salt;
    }

    public static (byte[] PrivateKey, byte[] PublicKey) GenerateX25519Pair()
    {
        var privateKey = new X25519PrivateKeyParameters(new SecureRandom());
        var publicKey = privateKey.GeneratePublicKey();
        var sk = new byte[X25519PrivateKeyParameters.SecretSize];
        var pk = new byte[X25519PublicKeyParameters.KeySize];
        privateKey.Encode(sk, 0);
        publicKey.Encode(pk, 0);
        return (sk, pk);
    }

    public static byte[] SharedSecretFromPkcs8(byte[] privateKeyPkcs8, byte[] publicKeySpki)
    {
        if (privateKeyPkcs8.Length != X25519PrivateKeyParameters.SecretSize)
            throw new ArgumentException("La llave privada X25519 debe tener 32 bytes.", nameof(privateKeyPkcs8));
        if (publicKeySpki.Length != X25519PublicKeyParameters.KeySize)
            throw new ArgumentException("La llave publica X25519 debe tener 32 bytes.", nameof(publicKeySpki));

        var privateKey = new X25519PrivateKeyParameters(privateKeyPkcs8, 0);
        var publicKey = new X25519PublicKeyParameters(publicKeySpki, 0);
        var shared = new byte[X25519PrivateKeyParameters.SecretSize];
        privateKey.GenerateSecret(publicKey, shared, 0);
        return shared;
    }

    public static SessionKeys DeriveSession(byte[] z, byte[] salt, RcaContext ctx)
    {
        var prk = HkdfExtract(salt, z);
        return new SessionKeys
        {
            Z = z.ToArray(),
            Salt = salt.ToArray(),
            Prk = prk,
            KPermBase = HkdfExpand(prk, BuildInfo("RCA|perm|v2", ctx), 32),
            KKernelBase = HkdfExpand(prk, BuildInfo("RCA|kernel|v2", ctx), 32),
            KMac = HkdfExpand(prk, BuildInfo("RCA|mac|v2", ctx), 32),
            KSeed = HkdfExpand(prk, BuildInfo("RCA|drbg|v2", ctx), 32)
        };
    }

    public static RoundKeys DeriveRound(SessionKeys session, RcaContext ctx, uint roundIndex)
    {
        var kPerm = HkdfExpand(session.Prk, BuildRoundInfo("RCA|perm|v2|round=", roundIndex, ctx), 32);
        var kKernel = HkdfExpand(session.Prk, BuildRoundInfo("RCA|kernel|v2|round=", roundIndex, ctx), 32);
        var mooreByChannel = new ushort[3][][];
        for (var ch = 0; ch < 3; ch++)
        {
            mooreByChannel[ch] = new ushort[2][];
            for (var k = 0; k < 2; k++)
                mooreByChannel[ch][k] = DeriveMoore(kKernel, (byte)(1 + ch * 2 + k));
        }
        return new RoundKeys
        {
            KPerm = kPerm,
            KKernel = kKernel,
            PermIndex = (byte)(SHA256.HashData(kPerm)[0] & 0x7F),
            MooreByChannel = mooreByChannel
        };
    }

    private static ushort[] DeriveMoore(byte[] kKernel, byte tag)
    {
        var material = new byte[33];
        Array.Copy(kKernel, material, 32);
        material[32] = tag;
        var digest = SHA256.HashData(material);
        var coeffs = new ushort[8];
        for (var i = 0; i < 8; i++)
        {
            var w = BinaryPrimitives.ReadUInt16LittleEndian(digest.AsSpan(i * 2, 2));
            coeffs[i] = (ushort)((w % 256) + 1);
        }
        return coeffs;
    }

    private static byte[] BuildInfo(string label, RcaContext ctx)
    {
        using var ms = new MemoryStream();
        ms.Write(Encoding.ASCII.GetBytes(label));
        WriteInfoSuite(ms, ctx);
        return ms.ToArray();
    }

    private static byte[] BuildRoundInfo(string label, uint roundIndex, RcaContext ctx)
    {
        using var ms = new MemoryStream();
        ms.Write(Encoding.ASCII.GetBytes(label));
        Span<byte> u32 = stackalloc byte[4];
        BinaryPrimitives.WriteUInt32LittleEndian(u32, roundIndex);
        ms.Write(u32);
        WriteInfoSuite(ms, ctx);
        return ms.ToArray();
    }

    private static void WriteInfoSuite(Stream stream, RcaContext ctx)
    {
        stream.Write(Encoding.ASCII.GetBytes("RCA|ctx|v2"));
        Span<byte> u32 = stackalloc byte[4];
        Span<byte> u16 = stackalloc byte[2];
        BinaryPrimitives.WriteUInt32LittleEndian(u32, ctx.Height);
        stream.Write(u32);
        BinaryPrimitives.WriteUInt32LittleEndian(u32, ctx.Width);
        stream.Write(u32);
        BinaryPrimitives.WriteUInt16LittleEndian(u16, ctx.Channels);
        stream.Write(u16);
        BinaryPrimitives.WriteUInt16LittleEndian(u16, ctx.Rounds);
        stream.Write(u16);
    }

    private static byte[] HkdfExtract(byte[] salt, byte[] ikm)
    {
        using var hmac = new HMACSHA256(salt.Length == 0 ? new byte[32] : salt);
        return hmac.ComputeHash(ikm);
    }

    private static byte[] HkdfExpand(byte[] prk, byte[] info, int length)
    {
        using var hmac = new HMACSHA256(prk);
        var okm = new byte[length];
        var t = Array.Empty<byte>();
        var offset = 0;
        byte counter = 1;
        while (offset < length)
        {
            var block = new byte[t.Length + info.Length + 1];
            Buffer.BlockCopy(t, 0, block, 0, t.Length);
            Buffer.BlockCopy(info, 0, block, t.Length, info.Length);
            block[^1] = counter++;
            t = hmac.ComputeHash(block);
            var copy = Math.Min(t.Length, length - offset);
            Buffer.BlockCopy(t, 0, okm, offset, copy);
            offset += copy;
        }
        return okm;
    }
}
