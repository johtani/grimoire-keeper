FROM python:3.13-slim

WORKDIR /app

# uvのインストール
RUN pip install uv

# 依存関係ファイルをコピー
COPY pyproject.toml ./
COPY uv.lock* ./

# 依存関係のインストール
RUN uv sync --frozen

# アプリケーションコードをコピー
COPY src/ ./src/

# ポート公開
EXPOSE 8000

# アプリケーション実行
CMD ["uv", "run", "uvicorn", "grimoire_api.main:app", "--host", "0.0.0.0", "--port", "8000"]