FROM nvidia/cuda:12.2.0-base-ubuntu22.04
WORKDIR /app
COPY requirements.txt requirements.txt
RUN apt-get update && apt-get install -y python3 python3-pip && pip3 install --extra-index-url https://download.pytorch.org/whl/cu126 --no-cache-dir --upgrade -r requirements.txt
COPY . /app
CMD ["fastapi", "run", "api.py", "--host", "0.0.0.0", "--port", "8081", "--workers", "1"]