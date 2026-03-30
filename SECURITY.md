# セキュリティガイドライン

## gitに含めてはいけないファイル

### 機密情報
- `~/.config/bws.env` - `BWS_ACCESS_TOKEN`（ホームディレクトリで管理、リポジトリ外）
- `.env` - 非秘密の設定値（APIキー類はBitwarden Secrets Managerで管理）
- `*.key`, `*.pem` - 秘密鍵
- `*.db`, `*.sqlite` - データベースファイル
- `*.log` - ログファイル（個人情報含む可能性）

### 自動生成ファイル
- `__pycache__/` - Pythonキャッシュ
- `.pytest_cache/` - テストキャッシュ
- `htmlcov/` - カバレッジレポート
- `dist/`, `build/` - ビルド成果物

## Amazon Q のセキュリティ

### 保護される情報
- APIキー、トークン、パスワード
- 個人識別情報（PII）
- 機密データ

### Amazon Q の動作
- ファイル読み込み時に自動でAPIキーを検出・マスク
- 機密情報は `<credential>` 等に置換
- 学習データには機密情報を含めない

### 推奨事項
- Bitwarden Secrets ManagerでAPIキー・トークンを管理
- `BWS_ACCESS_TOKEN` は `~/.config/bws.env` に保存（リポジトリ外、`chmod 600` 推奨）
- `.env.example` でテンプレート提供（非秘密の設定値のみ記載）
- 非秘密の設定値は `.env` に記載（gitignore対象）
- コード内にハードコードしない
- 定期的なキーローテーション