FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TORCH_CUDA_ARCH_LIST="6.1" \
    NEMO_EXCLUDE_APEX=1

WORKDIR /app

# 1. System packages: gcc/build-essential, Audio, and Wayland clipboard
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3 \
    python3-pip \
    python3-dev \
    git \
    bash \
    ca-certificates \
    ffmpeg \
    libsndfile1 \
    libportaudio2 \
    portaudio19-dev \
    alsa-utils \
    pulseaudio-utils \
    wl-clipboard \
    && rm -rf /var/lib/apt/lists/*

RUN ln -s /usr/bin/python3 /usr/bin/python

# 2. PyTorch CUDA 12.1 (preserves Pascal sm_61 kernel binaries)
RUN pip3 install --upgrade pip setuptools wheel && \
    pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 3. Audio, hotkey, and clipboard Python packages
RUN pip3 install \
    sounddevice \
    soundfile \
    numpy \
    pyperclip \
    evdev

# 4. NVIDIA NeMo ASR
RUN pip3 install cython && \
    pip3 install "nemo_toolkit[asr]" --extra-index-url https://download.pytorch.org/whl/cu121

# 5. Dictator Application Script
COPY dictator.py /app/dictator.py

CMD ["python", "/app/dictator.py"]