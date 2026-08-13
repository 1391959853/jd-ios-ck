FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖（如果需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用（只复制 app.py）
COPY app.py .

# 暴露端口
EXPOSE 5000

# 启动
CMD ["python", "app.py"]
