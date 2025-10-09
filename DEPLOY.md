# Grimoire Keeper デプロイ手順

## 事前準備

### 1. システム要件
- Ubuntu 20.04+ 
- Docker & Docker Compose
- 最低2GB RAM、10GB ディスク容量

### 2. 必要なAPIキー
- **OpenAI API Key** (埋め込み用)
- **Google API Key** (Gemini LLM用)  
- **Jina API Key** (コンテンツ抽出用)
- **Slack Bot Token** (xoxb-...)
- **Slack Signing Secret**
- **Slack App Token** (xapp-...)

## デプロイ手順

### 1. サーバー準備
```bash
# Docker インストール（公式リポジトリ使用 - 公式ドキュメントと同じ作業）
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# リポジトリ設定
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Docker インストール
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable docker
sudo usermod -aG docker $USER
# ログアウト・ログインして権限反映

# プロジェクトクローン
git clone <your-repo-url> grimoire-keeper
cd grimoire-keeper
```

### 2. Slack App設定（デプロイ前に必須）

#### 2.1. Slack App作成
1. https://api.slack.com/apps → "Create New App"
2. "From scratch" → アプリ名・ワークスペース選択

#### 2.2. Socket Mode設定
**Socket Mode:**
1. "Socket Mode" → Enable Socket Mode: ON
2. "Generate Token and Scopes" → Token Name: "grimoire-app-token"
3. Scopes: `connections:write` → Generate
4. App-Level Tokenをコピー → 後で`SLACK_APP_TOKEN`に設定

#### 2.3. Bot設定
**OAuth & Permissions:**
1. Bot Token Scopes: `app_mentions:read`, `chat:write`, `commands`
2. Install App to Workspace
3. Bot User OAuth Tokenをコピー → 後で`SLACK_BOT_TOKEN`に設定

**Event Subscriptions:**
1. Enable Events: ON
2. Subscribe to bot events: `app_mention`

**Slash Commands:**
1. Command: `/grimoire`
2. Description: "Grimoire Keeper URL処理"
3. Usage Hint: `[URL] [memo]`

**Interactivity & Shortcuts:**
1. Interactivity: ON

**Basic Information:**
1. Signing Secretをコピー → 後で`SLACK_SIGNING_SECRET`に設定

### 3. 環境設定
```bash
# 環境変数設定
cp .env.example .env
nano .env  # 上記で取得したAPIキー・トークンを設定

# 必須設定項目:
# OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=...
# JINA_API_KEY=...
# SLACK_BOT_TOKEN=xoxb-...        # 手順2.3で取得
# SLACK_SIGNING_SECRET=...        # 手順2.3で取得  
# SLACK_APP_TOKEN=xapp-...        # 手順2.2で取得
```

### 4. デプロイ実行
```bash
# 自動デプロイ
chmod +x scripts/deploy.sh
./scripts/deploy.sh

# デプロイスクリプトは以下を自動実行:
# - コンテナビルド・起動
# - Weaviate接続確認
# - SQLiteテーブル作成
# - Weaviateスキーマ作成
# - 全サービス動作確認
```

### 5. 動作確認
```bash
# サービス状態確認
docker compose -f docker-compose.prod.yml ps

# ログ確認
docker compose -f docker-compose.prod.yml logs -f

# API動作確認
curl http://localhost:8000/api/v1/health

# Weaviate動作確認  
curl http://localhost:8089/v1/meta
```

## 補足: Slack App詳細設定

上記手順2で設定したSlack Appの詳細情報：

### 必要なスコープ
- `app_mentions:read`: メンション受信
- `chat:write`: メッセージ送信
- `commands`: スラッシュコマンド

### Socket Modeの利点
- 外部URLエンドポイント不要
- ファイアウォール設定簡素化
- WebSocket接続でリアルタイム通信

## 運用管理

### サービス管理
```bash
# 停止
docker compose -f docker-compose.prod.yml down

# 再起動
docker compose -f docker-compose.prod.yml restart

# 更新デプロイ
git pull
./scripts/deploy.sh
```

### ログ監視
```bash
# リアルタイムログ
docker compose -f docker-compose.prod.yml logs -f

# エラーログのみ
docker compose -f docker-compose.prod.yml logs --tail=100 | grep ERROR
```

### データバックアップ
```bash
# データベースバックアップ
sudo cp -r /opt/grimoire-keeper-data /backup/$(date +%Y%m%d)

# 復元
sudo cp -r /backup/20241201 /opt/grimoire-keeper-data
```

## トラブルシューティング

### よくある問題

**1. APIキーエラー**
```bash
# .envファイル確認
cat .env | grep -E "(OPENAI|GOOGLE|JINA|SLACK)"
```

**2. コンテナ起動失敗**
```bash
# ログ確認
docker compose -f docker-compose.prod.yml logs api
docker compose -f docker-compose.prod.yml logs bot
```

**3. Slack接続エラー**
```bash
# Bot用環境変数確認
docker compose -f docker-compose.prod.yml exec bot env | grep SLACK
```

**4. データベース問題**
```bash
# データディレクトリ権限確認
ls -la /opt/grimoire-keeper-data/
```

### ポート使用状況
- **8000**: API (外部公開)
- **8089**: Weaviate (内部のみ)
- **Bot**: Socket Mode (外部ポート不要、WebSocket接続)

## セキュリティ

### 推奨設定
- ファイアウォール設定 (8000番ポートのみ公開)
- SSL/TLS証明書設定 (Let's Encrypt推奨)
- 定期的なAPIキーローテーション
- ログ監視・アラート設定

### nginx設定例
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```