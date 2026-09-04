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

# 展開後のport設定を確認（Host IPがすべて127.0.0.1であること）
docker compose -f docker-compose.prod.yml config

# ログ確認
docker compose -f docker-compose.prod.yml logs -f

# API動作確認
curl http://localhost:8000/api/v1/health

# Weaviate動作確認  
curl http://localhost:8089/v1/meta
```

Web (`8001`)、API (`8000`)、Weaviate HTTP (`8089`) および gRPC (`50051`) は、
すべてホストの `127.0.0.1` にだけ bind されます。デプロイ先ホスト以外から直接接続
できる状態は想定していません。管理画面はデプロイ先ホスト上で
`http://localhost:8001` を開いて利用します。

Slack Bot は Socket Mode で Slack へ outbound 接続し、外部からの inbound port を
必要としません。Bot から API への通信には、公開portではなく Compose 内部networkの
`http://api:8000` を使用します。API と worker から Weaviate への通信も同様に
`weaviate:8080` を使用します。

### 6. 公開範囲の確認

デプロイ後、待受addressが `127.0.0.1` に限定されていることを確認します。

```bash
# Dockerが公開するportとHost IPを確認
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml config

# ホストの実際の待受socketを確認
sudo ss -lntp | grep -E ':(8000|8001|8089|50051)\b'

# loopback経由でWeb/API/Weaviateへ接続できることを確認
curl -f http://127.0.0.1:8001/api/v1/health
curl -f http://127.0.0.1:8000/api/v1/health
curl -f http://127.0.0.1:8089/v1/.well-known/ready

# ufwを利用している場合は、管理portを許可するルールがないことを確認
sudo ufw status numbered
```

`ss` の Local Address:Port は `127.0.0.1:8000`、`127.0.0.1:8001`、
`127.0.0.1:8089`、`127.0.0.1:50051` である必要があります。`0.0.0.0`、`[::]`、
またはホストの外部向けIPで待ち受けている場合は、運用を開始せず Compose 設定と
firewall ruleを見直してください。これらのportを ufw などで外部向けに許可しないで
ください。

### 7. リモートから管理する場合（明示的な opt-in）

リモート管理が必要な場合も Compose の bind address は変更せず、アクセスを許可した
管理者だけが利用できる SSH tunnel または VPN を別途構成します。例えば Web UI だけを
SSH tunnel 経由で利用する場合は、管理端末で次を実行します。

```bash
ssh -N -L 8001:127.0.0.1:8001 <user>@<deploy-host>
```

接続中は管理端末の `http://127.0.0.1:8001` からアクセスできます。API や Weaviate の
保守が必要な場合だけ、同じ方法で必要なportを個別に転送してください。SSH serverやVPNの
認証、接続元制限、監査は運用環境のポリシーに従って設定します。

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

`deploy.sh` はサービス停止後にSQLiteを読み取り専用で検査します。スキーマ移行が必要な
場合だけ `/opt/grimoire-keeper-data/backups/database-before-schema-<timestamp>` へ
自動バックアップし、単独プロセスで移行と検証を完了してからサービスを起動します。
未知・破損・将来スキーマを検出した場合は、バックアップや移行を推測で進めず
デプロイを中止します。

スキーマ移行がなくてもバックアップする場合:

```bash
FORCE_SQLITE_BACKUP=true ./scripts/deploy.sh
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
- **8001**: Web UI (`127.0.0.1` のみ)
- **8000**: API (`127.0.0.1` のみ。BotはCompose内部の`api:8000`を使用)
- **8089 / 50051**: Weaviate HTTP / gRPC (`127.0.0.1` のみ)
- **Bot**: Socket Modeによるoutbound接続 (外部からのinbound port不要)

## セキュリティ

### 推奨設定
- API、Web UI、Weaviate のhost bindを`127.0.0.1`から変更しない
- firewallで管理port (`8000`、`8001`、`8089`、`50051`) を外部公開しない
- リモート管理は接続元を制限したSSH tunnelまたはVPNで明示的に有効化する
- 定期的なAPIキーローテーション
- ログ監視・アラート設定

Weaviate は匿名アクセスが有効なため、loopbackおよびCompose内部networkから到達可能な
構成を前提とします。loopbackは同一ホスト上の別ユーザーやプロセスを隔離しないため、
信頼できないユーザーが同居するホストでは追加の認証・アクセス制御を検討してください。
