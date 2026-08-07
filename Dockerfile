# Backend – Python 3.11 + CUDA 12.8 + SadTalker (compatible RTX 5000 Blackwell)
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Venv de SadTalker (fuera de /app para no conflictar con el bind-mount de código)
    SADTALKER_VENV=/opt/sadtalker_venv

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common ca-certificates curl git && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y --no-install-recommends \
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
