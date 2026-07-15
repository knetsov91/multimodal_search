FROM nvidia/cuda:12.2.0-base-ubuntu22.04
WORKDIR /app
COPY requirements.txt requirements.txt
RUN apt-get update && apt-get install -y python3 python3-pip && pip3 install --extra-index-url https://download.pytorch.org/whl/cu126 --no-cache-dir --upgrade -r requirements.txt
COPY . /app
RUN chmod +x /app/start.sh
CMD ["/app/start.sh"]