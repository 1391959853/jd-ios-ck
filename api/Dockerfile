FROM python:3.9-slim

WORKDIR /app

# 修正：修改正确的源配置文件 debian.sources
RUN sed -i 's@http://deb.debian.org@https://mirrors.aliyun.com@g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's@http://security.debian.org@https://mirrors.aliyun.com@g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# pip 换源（阿里云）
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

COPY app.py .
EXPOSE 9090
CMD ["python", "app.py"]
