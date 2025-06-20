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

# アプリケーション実行
CMD ["uv", "run", "python", "-m", "grimoire_bot.main"]