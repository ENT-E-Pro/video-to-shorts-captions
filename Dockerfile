FROM apify/actor-python:3.13
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Bake Whisper models so runs start without a download (others fetched from Hugging Face on first use).
ENV HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=/opt/hf
RUN python3 -c "from faster_whisper import WhisperModel as W; [W(m, device='cpu', compute_type='int8') for m in ('base','small')]"
COPY . ./
CMD ["python3", "-m", "src"]
