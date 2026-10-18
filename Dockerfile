# 1. Base image: CUDA 12.1 runtime maintains full Pascal (sm_61 / GTX 1070) support
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TORCH_CUDA_ARCH_LIST="6.1" \
    NEMO_EXCLUDE_APEX=1

WORKDIR /app

# 2. System dependencies (Audio, Clipboard for X11 & Wayland, Build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    git \
    bash \
    curl \
    ca-certificates \
    ffmpeg \
    libsndfile1 \
    libportaudio2 \
    portaudio19-dev \
    alsa-utils \
    pulseaudio-utils \
    xclip \
    wl-clipboard \
    && rm -rf /var/lib/apt/lists/*

RUN ln -s /usr/bin/python3 /usr/bin/python

# 3. Node.js 22 LTS (Required for Claude Code and OpenCode CLI)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# 4. PyTorch cu121 with guaranteed sm_61 Pascal kernel binaries
RUN pip3 install --upgrade pip setuptools wheel && \
    pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 5. Audio recording, input capture, and clipboard libraries
RUN pip3 install \
    sounddevice \
    soundfile \
    numpy \
    pynput \
    pyperclip

# 6. NVIDIA NeMo ASR (uses --extra-index-url to prevent overwriting cu121 PyTorch)
RUN pip3 install cython && \
    pip3 install "nemo_toolkit[asr]" --extra-index-url https://download.pytorch.org/whl/cu121

# 7. Global CLI agents
RUN npm install -g \
    @anthropic-ai/claude-code \
    @opencode/cli

# 8. Claude Code configuration from build context
RUN mkdir -p /root/.claude
COPY config/settings.json /root/.claude/settings.json
COPY config/claude-statusline.sh /root/.claude/claude-statusline.sh
RUN chmod +x /root/.claude/claude-statusline.sh

# 9. Application script
COPY dictator.py /app/dictator.py

CMD ["python", "/app/dictator.py"]