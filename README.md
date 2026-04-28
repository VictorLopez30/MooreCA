# TT - Guia de ejecucion

Este documento resume los comandos principales para:

- compilar las implementaciones en `C`, `Java` y `C#`
- ejecutar cifrado y descifrado desde consola
- levantar el backend y frontend web de `v2/`
- ejecutar el experimento de variacion de rondas

## 1. Dependencias

Instalar o verificar estas herramientas:

- `python3`
- `pip`
- `gcc`
- `libcrypto` / OpenSSL de desarrollo
- `javac` y `java`
- `dotnet`
- `ffmpeg`
- `ffprobe`

Paquetes Python para el backend:

```bash
pip install flask flask-cors pillow
```

## 2. Compilacion de C

### Cifrador en C

```bash
mkdir -p v2/build
gcc -std=c11 -O2 c/cifrado.c c/automata.c c/permutaciones.c c/llaves.c -I c -lcrypto -o v2/build/cifrador_c
```

### Descifrador en C

```bash
mkdir -p v2/build
gcc -std=c11 -O2 c/descifrado.c c/automata.c c/permutaciones.c c/llaves.c -I c -lcrypto -o v2/build/descifrador_c
```

## 3. Compilacion de Java

```bash
mkdir -p v2/build/java
javac -d v2/build/java java/*.java
```

## 4. Compilacion de C#

El backend `v2/app.py` genera y compila los proyectos de `C#` automaticamente. Si quieres disparar la compilacion manualmente:

```bash
dotnet build v2/build/cs/Cifrado/Cifrado.csproj
dotnet build v2/build/cs/Descifrado/Descifrado.csproj
```

Nota: esos `.csproj` deben existir previamente. La forma normal de generarlos es correr primero el backend o `experimento1.py`.

## 5. Cifrado desde consola

### C

Modo imagen sin perdida (`PNG`, `BMP`, `TIFF`):

```bash
./v2/build/cifrador_c <in.png|in.bmp|in.tif|in.tiff> <out_cipher_u16.bin> <out_preview.png|bmp|tif|tiff|raw> <rondas>
```

Ejemplo:

```bash
./v2/build/cifrador_c black.bmp salida_c.bin preview_c.png 10
```

Modo sesion compartida:

```bash
./v2/build/cifrador_c <in.png|in.bmp|in.tif|in.tiff> <out_cipher_u16.bin> <out_preview.png|bmp|tif|tiff|raw> <rondas> <Z_hex_64> <salt_hex_64>
```

### Java

```bash
java -cp v2/build/java Cifrado <in.png|in.bmp|in.tif|in.tiff> <out_cipher_u16.bin> <out_preview.png|bmp|tif|tiff|raw> <rondas>
```

Ejemplo:

```bash
java -cp v2/build/java Cifrado black.bmp salida_java.bin preview_java.png 10
```

### C#

Cuando el backend ya genero el proyecto:

```bash
dotnet v2/build/cs/Cifrado/bin/Debug/net10.0/Cifrado.dll <in.png|in.bmp|in.tif|in.tiff> <out_cipher_u16.bin> <out_preview.png|bmp|tif|tiff|raw> <rondas>
```

Ejemplo:

```bash
dotnet v2/build/cs/Cifrado/bin/Debug/net10.0/Cifrado.dll black.bmp salida_cs.bin preview_cs.png 10
```

## 6. Descifrado desde consola

### C

```bash
./v2/build/descifrador_c <x_r-1_u16.bin> <x_r_u16.bin> <out.png|bmp|tif|tiff|raw> <ancho> <alto> <canales> <rondas> <Z_hex_64> <salt_hex_64>
```

### Java

```bash
java -cp v2/build/java Descifrado <x_r-1_u16.bin> <x_r_u16.bin> <out.png|bmp|tif|tiff|raw> <ancho> <alto> <canales> <rondas> <Z_hex_64> <salt_hex_64>
```

### C#

```bash
dotnet v2/build/cs/Descifrado/bin/Debug/net10.0/Descifrado.dll <x_r-1_u16.bin> <x_r_u16.bin> <out.png|bmp|tif|tiff|raw> <ancho> <alto> <canales> <rondas> <Z_hex_64> <salt_hex_64>
```

## 7. Backend web

Desde la raiz del proyecto:

```bash
python3 v2/app.py
```

El backend queda en:

```text
http://127.0.0.1:5000
```

## 8. Frontend web

### Opcion simple: servidor estatico con Python

```bash
cd v2
python3 -m http.server 8000
```

Abrir en navegador:

```text
http://127.0.0.1:8000
```

## 9. Carpeta de resultados del frontend/backend

Los resultados persistentes de la app web se guardan en:

```text
v2/Resultados/
```

## 10. Ejecucion del experimento 1

`experimento1.py` ejecuta el cifrado con los tres lenguajes variando las rondas:

```text
1, 5, 10, 15, ..., 50
```

Genera:

- una carpeta en `Experimentos/`
- las imagenes cifradas por lenguaje y por numero de rondas
- un `resultados.csv` con:
  - `rondas`
  - `lenguaje`
  - `tiempo_promedio_s`
  - `desviacion_estandar_s`
  - `entropia`
  - `chi_cuadrada`
  - `correlacion`

### Ejecucion basica

```bash
python3 experimento1.py <imagen.png|imagen.bmp|imagen.tif|imagen.tiff>
```

Ejemplo:

```bash
python3 experimento1.py black.bmp
```

### Con nombre de carpeta de salida

```bash
python3 experimento1.py black.bmp --output-name experimento_rondas
```

### Con numero de repeticiones por configuracion

```bash
python3 experimento1.py black.bmp --repetitions 10
```

## 11. Ejecucion del experimento 2

`experimento2.py` varia el tamano de la imagen con un numero fijo de rondas.

### Ejecucion basica

```bash
python3 experimento2.py black.bmp
```

### Fijando rondas y tamanos

```bash
python3 experimento2.py black.bmp --rounds 10 --sizes 256 512 1024 2048
```

### Con repeticiones

```bash
python3 experimento2.py black.bmp --rounds 10 --sizes 256 512 1024 --repetitions 10
```

## 12. Ejecucion del experimento 3

`experimento3.py` estima la relacion entre tiempo y `N * R`.

### Ejecucion basica

```bash
python3 experimento3.py black.bmp
```

### Con combinaciones personalizadas

```bash
python3 experimento3.py black.bmp --sizes 256 512 1024 --rounds 1 5 10 20 50
```

El experimento genera:

- `resultados_detalle.csv`
- `regresion.csv`

## 13. Ejecucion del experimento 4

`experimento4.py` compara los tres lenguajes con una sola imagen y un numero fijo de rondas.

### Sesion compartida

```bash
python3 experimento4.py black.bmp --rounds 10 --session-mode shared
```

### Sesion independiente

```bash
python3 experimento4.py black.bmp --rounds 10 --session-mode independent
```

## 14. Ejecucion del experimento 5

`experimento5.py` compara el impacto del formato de entrada usando `PNG`, `BMP` y `TIFF`.

### Ejecucion basica

```bash
python3 experimento5.py black.bmp
```

### Fijando rondas

```bash
python3 experimento5.py black.bmp --rounds 10 --repetitions 10
```

## 15. Ejecucion del experimento 6

`experimento6.py` verifica cumplimiento de cuota computacional.

### Ejecucion basica

```bash
python3 experimento6.py black.bmp
```

### Cuota personalizada

```bash
python3 experimento6.py black.bmp --sizes 512 1024 2048 --rounds 10 20 --time-limit 5.0 --repetitions 10
```

El CSV de salida incluye la columna:

- `cumple_cuota`

## 16. Flujo rapido recomendado

### Levantar backend

```bash
python3 v2/app.py
```

### Levantar frontend

```bash
cd v2
python3 -m http.server 8000
```

### Correr experimento

Desde la raiz:

```bash
python3 experimento1.py black.bmp --repetitions 10
```

## 17. Notas

- Los formatos soportados para las pruebas actuales son:
  - `PNG`
  - `BMP`
  - `TIFF`
- El backend y los scripts de experimentos compilan automaticamente lo necesario cuando aplica, pero sigue siendo util tener claros los comandos manuales.
