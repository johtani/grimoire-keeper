# Grimoire Keeper デプロイ手順

## 事前準備

### 1. システム要件
- Ubuntu 20.04+ 
- Docker & Docker Compose
- 最低2GB RAM、10GB ディスク容量

### 2. 必要なAPIキー・トークン
- **Bitwarden Secrets Manager Access Token** (`BWS_ACCESS_TOKEN`)

> API キー・Slack トークンは Bitwarden Secrets Manager で管理します。
> 詳細は [CLAUDE.md](CLAUDE.md) の「設定とシークレット」セクションを参照してください。

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
4. App-Level Tokenをコピー → Bitwardenの`GRIMOIRE_KEEPER_SLACK_APP_TOKEN`に登録

#### 2.3. Bot設定
**OAuth & Permissions:**
1. Bot Token Scopes: `app_mentions:read`, `chat:write`, `commands`
2. Install App to Workspace
3. Bot User OAuth Tokenをコピー → Bitwardenの`GRIMOIRE_KEEPER_SLACK_BOT_TOKEN`に登録

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
1. Signing Secretをコピー → Bitwardenの`GRIMOIRE_KEEPER_SLACK_SIGNING_SECRET`に登録

### 3. 環境設定
```bash
# BWS_ACCESS_TOKENを保存
mkdir -p ~/.config
echo 'BWS_ACCESS_TOKEN=your-access-token' > ~/.config/bws.env
chmod 600 ~/.config/bws.env

# 非秘密の設定値を .env に記載
cp .env.example .env
nano .env

# 起動（bws runがBitwardenからシークレットを取得してdocker composeを起動）
bash scripts/start.sh -d
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

#### 停止
```bash
docker compose -f docker-compose.prod.yml down
```

#### 再起動（コード変更なし）
```bash
# ❗ docker compose restart は使わないこと
# restartはコンテナを再起動するだけなので、
# Bitwardenからのシークレット取得が実行されず環境変数が欠落する
bash scripts/start.sh -d
```

#### 更新デプロイ（コード変更あり・イメージ再ビルド）
```bash
# ❗ start.sh は不要。deploy.sh がビルド・起動・シークレット注入をすべて行う
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

**1. 環境変数エラー**
```bash
# BWS_ACCESS_TOKENが設定されているか確認
cat ~/.config/bws.env
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