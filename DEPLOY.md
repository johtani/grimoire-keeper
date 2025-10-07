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

### 2. 環境設定
```bash
# 環境変数設定
cp .env.example .env
nano .env  # APIキーを設定

# 必須設定項目:
# OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=...
# JINA_API_KEY=...
# SLACK_BOT_TOKEN=xoxb-...
# SLACK_SIGNING_SECRET=...
# SLACK_APP_TOKEN=xapp-...
```

### 3. デプロイ実行
```bash
# 自動デプロイ
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

### 4. 動作確認
```bash
# サービス状態確認
docker compose -f docker-compose.prod.yml ps

# ログ確認
docker compose -f docker-compose.prod.yml logs -f

# API動作確認
curl http://localhost:8000/api/v1/health

# Weaviate動作確認  
curl http://localhost:8080/v1/meta
```

## Slack App設定

### 1. Slack App作成
1. https://api.slack.com/apps → "Create New App"
2. "From scratch" → アプリ名・ワークスペース選択

### 2. Bot設定
**OAuth & Permissions:**
- Bot Token Scopes: `app_mentions:read`, `chat:write`, `commands`
- Install App to Workspace

**Event Subscriptions:**
- Enable Events: ON
- Request URL: `https://your-domain.com/slack/events` (ngrok等)
- Subscribe to bot events: `app_mention`

**Slash Commands:**
- Command: `/grimoire`
- Request URL: `https://your-domain.com/slack/commands`

**Interactivity & Shortcuts:**
- Interactivity: ON
- Request URL: `https://your-domain.com/slack/interactive`

### 3. トークン取得
- **Bot User OAuth Token** → `SLACK_BOT_TOKEN`
- **Signing Secret** → `SLACK_SIGNING_SECRET`  
- **App-Level Token** → `SLACK_APP_TOKEN`

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
- **8080**: Weaviate (内部のみ)
- **Bot**: Socket Mode (外部ポート不要)

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