import java.awt.image.BufferedImage;
import java.io.File;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.imageio.ImageIO;

final class Common {
    static final int AUTOMATA_MOD_BASE = 257;
    static final int KEY_BYTES = 32;
    static final int SALT_BYTES = 32;

    enum BoundaryMode { PERIODIC, REFLECT, ADIABATIC }

    record BoundaryConfig(BoundaryMode top, BoundaryMode bottom, BoundaryMode left, BoundaryMode right) {}
    record RcaContext(int height, int width, int channels, int rounds) {}
    record LoadedImage(byte[] raw, int width, int height, int channels) {}

    static final class SessionFile {
        String width;
        String height;
        String channels;
        String rounds;
        String prevPath;
        String curPath;
        String zHex;
        String saltHex;

        static SessionFile parse(Path path) throws IOException {
            SessionFile s = new SessionFile();
            for (String rawLine : Files.readAllLines(path, StandardCharsets.UTF_8)) {
                String line = rawLine.trim();
                if (line.isEmpty() || line.startsWith("#")) continue;
                int idx = line.indexOf('=');
                if (idx <= 0) continue;
                String k = line.substring(0, idx);
                String v = line.substring(idx + 1);
                switch (k) {
                    case "ancho" -> s.width = v;
                    case "alto" -> s.height = v;
                    case "canales" -> s.channels = v;
                    case "rondas" -> s.rounds = v;
                    case "x_prev_path" -> s.prevPath = v;
                    case "x_cur_path" -> s.curPath = v;
                    case "z_hex" -> s.zHex = v;
                    case "salt_hex" -> s.saltHex = v;
                }
            }
            if (s.width == null || s.height == null || s.channels == null || s.rounds == null ||
                s.prevPath == null || s.curPath == null || s.zHex == null || s.saltHex == null) {
                throw new IOException("Archivo de sesion incompleto.");
            }
            return s;
        }

        void save(Path path) throws IOException {
            StringBuilder sb = new StringBuilder();
            sb.append("# Sesion de cifrado\n");
            sb.append("ancho=").append(width).append('\n');
            sb.append("alto=").append(height).append('\n');
            sb.append("canales=").append(channels).append('\n');
            sb.append("rondas=").append(rounds).append('\n');
            sb.append("x_prev_path=").append(prevPath).append('\n');
            sb.append("x_cur_path=").append(curPath).append('\n');
            sb.append("z_hex=").append(zHex).append('\n');
            sb.append("salt_hex=").append(saltHex).append('\n');
            Files.writeString(path, sb.toString(), StandardCharsets.UTF_8);
        }
    }

    static LoadedImage loadImageOrRaw(String path, Integer width, Integer height, Integer channels) throws Exception {
        String ext = extension(path);
        if (".png".equals(ext) || ".bmp".equals(ext) || ".tif".equals(ext) || ".tiff".equals(ext)) {
            BufferedImage img = ImageIO.read(new File(path));
            if (img == null) throw new IOException("No se pudo leer imagen: " + path);
            int w = img.getWidth();
            int h = img.getHeight();
            byte[] raw = new byte[w * h * 3];
            int p = 0;
            for (int y = 0; y < h; y++) {
                for (int x = 0; x < w; x++) {
                    int rgb = img.getRGB(x, y);
                    raw[p++] = (byte)((rgb >> 16) & 0xFF);
                    raw[p++] = (byte)((rgb >> 8) & 0xFF);
                    raw[p++] = (byte)(rgb & 0xFF);
                }
            }
            return new LoadedImage(raw, w, h, 3);
        }
        if (width == null || height == null || channels == null) {
            throw new IllegalArgumentException("Para .raw debes proporcionar ancho, alto y canales.");
        }
        return new LoadedImage(Files.readAllBytes(Path.of(path)), width, height, channels);
    }

    static void savePreview(byte[] raw, int width, int height, int channels, String path) throws Exception {
        String ext = extension(path);
        if ((".png".equals(ext) || ".bmp".equals(ext) || ".tif".equals(ext) || ".tiff".equals(ext)) && channels == 3) {
            BufferedImage img = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
            int p = 0;
            for (int y = 0; y < height; y++) {
                for (int x = 0; x < width; x++) {
                    int r = raw[p++] & 0xFF;
                    int g = raw[p++] & 0xFF;
                    int b = raw[p++] & 0xFF;
                    img.setRGB(x, y, (r << 16) | (g << 8) | b);
                }
            }
            String format = (".tif".equals(ext) || ".tiff".equals(ext)) ? "TIFF" : ext.substring(1);
            ImageIO.write(img, format, new File(path));
            return;
        }
        Files.write(Path.of(path), raw);
    }

    static void writeU16(Path path, short[] data) throws IOException {
        ByteBuffer bb = ByteBuffer.allocate(data.length * 2).order(ByteOrder.LITTLE_ENDIAN);
        for (short v : data) bb.putShort(v);
        Files.write(path, bb.array());
    }

    static short[] readU16(Path path) throws IOException {
        byte[] bytes = Files.readAllBytes(path);
        if ((bytes.length & 1) != 0) throw new IOException("Archivo u16 invalido");
        short[] data = new short[bytes.length / 2];
        ByteBuffer bb = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
        for (int i = 0; i < data.length; i++) data[i] = bb.getShort();
        return data;
    }

    static String extension(String path) {
        int idx = path.lastIndexOf('.');
        return idx >= 0 ? path.substring(idx).toLowerCase() : "";
    }
}
