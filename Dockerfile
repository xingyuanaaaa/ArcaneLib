FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建数据目录
RUN mkdir -p data static/uploads/software static/uploads/images

# 暴露端口
EXPOSE 5000

# 启动命令
CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120