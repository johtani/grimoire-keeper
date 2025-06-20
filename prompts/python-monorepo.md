# Python モノリポ構築プロンプト

uvを使用したPythonモノリポ構成を作成してください。

## 技術スタック
- Python 3.13
- uv（パッケージ管理）
- ruff（コード品質）
- pytest（テスト）

## 構成要件
- ワークスペース設定
- 共通ライブラリ（shared）
- 複数アプリケーション（apps/）
- 統一された開発ツール設定

## 設定内容
- pyproject.toml（ルート + 各アプリ）
- ruff設定（88文字、Python 3.13対応）
- pytest設定
- mypy設定