# Backend – Python 3.11 + CUDA 12.8 + SadTalker (compatible RTX 5000 Blackwell)
# Usamos la variante "base" (sin cuBLAS/cuDNN/NCCL del sistema): PyTorch se
# instala via pip mas abajo y trae sus propias copias de esas librerias CUDA
# como wheels (nvidia-cudnn-cu12, nvidia-cublas-cu12, etc.), asi que las del
# sistema quedarian sin usar — solo inflan la imagen unos ~4.2GB de mas.
FROM nvidia/cuda:12.8.0-base-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Venv de SadTalker (fuera de /app para no conflictar con el bind-mount de código)
    SADTALKER_VENV=/opt/sadtalker_venv

# ca-certificates primero y por separado: hace falta antes de poder confiar
# en ningun CA extra (ver mas abajo).
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# CAs locales extra (opcional): si en el equipo de build hay un antivirus o
# proxy que hace inspeccion TLS, se puede dejar el certificado en certs/ para
# que apt/pip confien en el. Vacio por defecto, no afecta a otros equipos.
COPY certs/ /usr/local/share/ca-certificates/extra/
RUN update-ca-certificates
# pip/requests/huggingface_hub usan el bundle de certifi por defecto, no el
# del sistema: forzamos que tambien usen el del sistema (ya actualizado).
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# Dependencias del sistema. Ubuntu 22.04 (jammy) ya trae Python 3.10 de
# fabrica en sus repos oficiales, asi que no hace falta el PPA de deadsnakes
# (ademas de innecesario, requeria una conexion HTTPS extra a Launchpad que
# fallaba por inspeccion TLS en algunas redes).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git \
    python3.10 python3.10-venv python3.10-dev python3-pip \
    ffmpeg \
    libsndfile1 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 libxext6 libxrender1 \
    libgomp1 && \
    rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 && \
    update-alternatives --install /usr/bin/python  python  /usr/bin/python3.10 1

WORKDIR /app

# Dependencias principales del proyecto
COPY requirements.txt .
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# Venv de SadTalker con PyTorch CUDA en /opt/sadtalker_venv
# (separado de /app para que el bind-mount de código no lo tape)
COPY vendor/sadtalker/requirements.txt /tmp/st_requirements.txt
RUN python3.10 -m venv /opt/sadtalker_venv && \
    /opt/sadtalker_venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/sadtalker_venv/bin/pip install --no-cache-dir \
        torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cu128 && \
    /opt/sadtalker_venv/bin/pip install --no-cache-dir \
        -r /tmp/st_requirements.txt && \
    /opt/sadtalker_venv/bin/pip install --no-cache-dir huggingface_hub

EXPOSE 8000

# --reload activa hot-reload: ediciones en el código se reflejan sin rebuild
CMD ["python3", "-m", "uvicorn", "api.server:app", \
     "--host", "0.0.0.0", "--port", "8000", "--reload"]
