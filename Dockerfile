# 单阶段构建。Zeabur 会自动检测根目录的 Dockerfile 并以 Docker 方式部署。
#
# 端口说明：Zeabur 给 Git 部署的服务注入的 PORT 默认是 8080，这里对齐；
#          代码从环境变量读端口，所以换平台只需改环境变量，不用改代码
#          （Hugging Face Spaces 需要 7860，把 PORT 设成 7860 即可）。
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app

# 先只拷依赖清单再装依赖：改业务代码时依赖层缓存不失效，构建快很多
COPY requirements.txt ./

# PIP_INDEX_URL 留成构建参数：默认官方 PyPI，海外构建机（Zeabur 等）直连没问题；
# 国内网络下构建慢或超时时，可以加
#   --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
# 来加速，不需要改这个文件。
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt

# 再拷运行时需要的代码与数据源
COPY app/ ./app/
COPY resume/ ./resume/
COPY static/ ./static/

# 创建非 root 用户；data/ 目录留给运行期自动生成的索引
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# 平台据此判断实例是否可用（k8s 探针 / Zeabur 健康检查都会打这个）
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8080')+'/health').read()"

# 走 app/main.py 的 __main__ 入口，端口从 PORT 环境变量读取
CMD ["python", "-m", "app.main"]
