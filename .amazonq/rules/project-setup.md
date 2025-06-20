# Grimoire Keeper プロジェクトルール

## 技術スタック
- Python 3.13
- uv (パッケージ管理)
- ruff (リント・フォーマット)
- pytest (テスト)
- FastAPI (バックエンドAPI)
- slack-bolt (Slackボット)
- Weaviate (ベクトルDB)

## プロジェクト構成
- モノリポ構成（uvワークスペース）
- devcontainer + Docker Compose
- 3つのサービス: workspace, bot, api, weaviate

## コーディング規約
- ruffを使用（black、isort、flake8の代替）
- line-length: 88
- Python 3.13対応
- 型ヒント必須（mypy）

## 開発環境
- devcontainer内で開発
- コマンド履歴永続化
- VSCode拡張: python, ruff, mypy
- 混合実行パターン推奨（インフラはコンテナ、アプリはdevcontainer）

## ディレクトリ構造
```
grimoire-keeper/
├── .devcontainer/
├── apps/bot/
├── apps/api/
├── shared/
└── pyproject.toml (ワークスペース設定)
```