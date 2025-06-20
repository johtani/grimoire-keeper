# devcontainer環境構築プロンプト

Python 3.13とuvを使用したモノリポ構成のdevcontainer環境を構築してください。

## 要件
- Python 3.13
- uvによるワークスペース管理
- ruff（black、isort、flake8の代替）
- Docker Composeで複数サービス
- コマンド履歴永続化
- VSCode拡張: python, ruff, mypy

## 構成
- workspace: 開発用コンテナ
- bot: Slackボット
- api: FastAPI
- weaviate: ベクトルDB

## ファイル
- .devcontainer/devcontainer.json
- .devcontainer/docker-compose.yml
- .devcontainer/setup.sh
- pyproject.toml（ワークスペース設定）