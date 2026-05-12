FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    ca-certificates \
    curl \
    default-jdk \
    ffmpeg \
    gcc \
    gnupg \
    libssl-dev \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN wget https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb -O /tmp/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && rm /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && apt-get install -y dotnet-sdk-10.0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

RUN python3 - <<'PY2'
import importlib.util
spec = importlib.util.spec_from_file_location('ttapp', '/app/v2/app.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
for fn in (mod.ensure_c_binaries, mod.ensure_java_build, mod.ensure_cs_projects):
    ok, msg = fn()
    if not ok:
        raise SystemExit(msg)
PY2

RUN dotnet restore /app/v2/build/cs/Cifrado/Cifrado.csproj \
    && dotnet build /app/v2/build/cs/Cifrado/Cifrado.csproj -c Release --no-restore \
    && dotnet restore /app/v2/build/cs/Descifrado/Descifrado.csproj \
    && dotnet build /app/v2/build/cs/Descifrado/Descifrado.csproj -c Release --no-restore

EXPOSE 5000

CMD ["sh", "-c", "gunicorn --chdir /app/v2 --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 2 --timeout 300 app:app"]

