FROM python:3.13-slim

WORKDIR /app

# uvのインストール
RUN pip install uv

# ポート公開
EXPOSE 8000

# 開発時はワークスペースをマウントするため、最小限の設定のみ
CMD ["sleep", "infinity"]