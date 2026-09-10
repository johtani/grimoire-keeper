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

| 対象 | Bitwarden の key 名 | process 内の環境変数 | 必須条件 |
|---|---|---|---|
| Worker | `GRIMOIRE_KEEPER_JINA_API_KEY` | `JINA_API_KEY` | 常時 |
| API / Worker / 再インデックス | `GRIMOIRE_KEEPER_OPENAI_API_KEY` | `OPENAI_API_KEY` | ベクトル検索・埋め込み生成時 |
| Worker | `GRIMOIRE_KEEPER_LLM_API_KEY` | `LLM_API_KEY` | cloud LLM 利用時 |
| Bot | `GRIMOIRE_KEEPER_SLACK_BOT_TOKEN` | `SLACK_BOT_TOKEN` | Bot 起動時 |
| Bot | `GRIMOIRE_KEEPER_SLACK_SIGNING_SECRET` | `SLACK_SIGNING_SECRET` | Bot 起動時 |
| Bot | `GRIMOIRE_KEEPER_SLACK_APP_TOKEN` | `SLACK_APP_TOKEN` | Bot 起動時 |

`docker-compose.prod.yml` が Bitwarden の prefix 付き key を process 内の prefix なし環境変数へ渡します。API は SQLite の設定だけで起動できますが、ベクトル検索と API コンテナでの再インデックスには OpenAI キーが必要です。ローカルの認証不要 LLM では `LLM_API_KEY=dummy` を非秘密設定として `.env` に置けます。それ以外の API key や token は `.env` に保存しません。

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

既定では Web (`8001`)、API (`8000`)、Weaviate HTTP (`8089`) および gRPC (`50051`) は、
すべてホストの `127.0.0.1` にだけ bind されます。管理画面はデプロイ先ホスト上で
`http://localhost:8001` を開いて利用します。Web UI だけを信頼済みネットワークへ
公開する場合は、`.env` で待受addressとportを明示します。

```dotenv
WEB_BIND_ADDRESS=192.168.1.100
WEB_PORT=8001
```

ホストのaddressが固定されていない環境では `WEB_BIND_ADDRESS=0.0.0.0` も指定できますが、
Web経由で認証のないAPIへアクセスできるため、必ずホストのfirewallや上位networkで
接続元を信頼済み端末に限定してください。インターネットへの直接公開はサポートしません。
設定変更は `docker compose -f docker-compose.prod.yml up -d --force-recreate web` で反映し、
`docker compose -f docker-compose.prod.yml port web 80` で公開先を確認します。API と
Weaviate のbind addressはこの設定では変更されません。

Slack Bot は Socket Mode で Slack へ outbound 接続し、外部からの inbound port を
必要としません。Bot から API への通信には、公開portではなく Compose 内部networkの
`http://api:8000` を使用します。API と worker から Weaviate への通信も同様に
`weaviate:8080` を使用します。

### 6. 公開範囲の確認

デプロイ後、待受addressが既定の `127.0.0.1` または意図した信頼済みinterfaceに
限定されていることを確認します。

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

既定では `ss` の Local Address:Port は `127.0.0.1:8000`、`127.0.0.1:8001`、
`127.0.0.1:8089`、`127.0.0.1:50051` である必要があります。`0.0.0.0`、`[::]`、
またはホストの外部向けIPで待ち受けている場合は、明示したWebの設定であることと
firewall ruleを確認してください。APIとWeaviateがloopback以外で待ち受けている場合は、
運用を開始せずCompose設定を見直してください。

### 7. リモートから管理する場合（明示的な opt-in）

リモート管理には、アクセスを許可した管理者だけが利用できる SSH tunnel または VPN を
推奨します。例えば既定のbind addressを変更せず、Web UIだけをSSH tunnel経由で利用する
場合は、管理端末で次を実行します。

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

SQLite・JSON・Weaviate は、すべての書き込みを止めた同じ時点のセットとして保存・復元します。
`deploy.sh` の SQLite 自動バックアップだけでは、サービス再開後の全体復旧はできません。
以下はリポジトリルートで Bash を使用する手順です。各ブロックは同じシェルで順に実行し、
途中で失敗したらサービスを停止したまま原因を確認してください。

#### 停止と保存対象の確認

手動の再インデックス・repair・移行コマンド、別 Compose やローカルで起動した API・worker、
自動実行ジョブも停止します。稼働中の Weaviate コンテナから実際の保存先と image を記録し、
`WEAVIATE_DATA_PATH` の変更やデータルート外の bind mount も対象にします。

```bash
set -euo pipefail
DATA_ROOT=/opt/grimoire-keeper-data
BACKUP_PARENT=/backup/grimoire-keeper
weaviate_container=$(docker compose -f docker-compose.prod.yml ps -q weaviate)
test -n "$weaviate_container"
WEAVIATE_DATA_PATH=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/weaviate"}}{{.Source}}{{end}}{{end}}' "$weaviate_container")
WEAVIATE_IMAGE=$(docker inspect --format '{{.Config.Image}}' "$weaviate_container")
test -n "$WEAVIATE_DATA_PATH"
# 対応する image はローカルに保持する。可変 tag を使用している場合は digest も記録する。
docker inspect --format '{{.Image}}' "$weaviate_container"
export WEAVIATE_DATA_PATH WEAVIATE_IMAGE
# 入口と書き込みプロセスを先に停止し、その後 Weaviate を正常停止する。
docker compose -f docker-compose.prod.yml stop web bot api worker
docker compose -f docker-compose.prod.yml stop weaviate
test -z "$(docker compose -f docker-compose.prod.yml ps --status running -q)"
```

停止後、次のブロックで `database`（WAL/SHM を含むディレクトリ全体）、`json`、
repair report を含む `migration`、Weaviate を保存します。バックアップはデータディレクトリの
外に置き、過去のバックアップを再帰コピーしません。`migration` がない旧環境は空として保存します。
全コピー成功時だけ `.partial` を外すため、途中失敗した保存先は復元に使用しません。

<!-- backup-files:start -->
```bash
sudo mkdir -p "$BACKUP_PARENT"
backup_tmp=$(sudo mktemp -d "$BACKUP_PARENT/backup-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.partial")
for name in database json; do
  sudo test -d "$DATA_ROOT/$name"
  sudo cp -a "$DATA_ROOT/$name" "$backup_tmp/$name"
done
sudo mkdir "$backup_tmp/migration"
if sudo test -d "$DATA_ROOT/migration"; then
  sudo cp -a "$DATA_ROOT/migration/." "$backup_tmp/migration/"
fi
sudo test -d "$WEAVIATE_DATA_PATH"
sudo cp -a "$WEAVIATE_DATA_PATH" "$backup_tmp/weaviate"
# .env は非秘密設定のみ。Bitwarden のシークレットは書き出さない。
sudo cp -a .env docker-compose.prod.yml "$backup_tmp/"
git rev-parse HEAD | sudo tee "$backup_tmp/git-commit.txt" >/dev/null
printf '%s\n' "$WEAVIATE_DATA_PATH" | sudo tee "$backup_tmp/weaviate-data-path.txt" >/dev/null
printf '%s\n' "$WEAVIATE_IMAGE" | sudo tee "$backup_tmp/weaviate-image.txt" >/dev/null
sudo touch "$backup_tmp/COMPLETE"
BACKUP_DIR=${backup_tmp%.partial}
sudo mv -T "$backup_tmp" "$BACKUP_DIR"
printf 'バックアップ完了: %s\n' "$BACKUP_DIR"
```
<!-- backup-files:end -->

`sudo` と `cp -a` で数値所有者・権限を保持します。バックアップ全体を `10001:10001` に
変更しません。通常の運用再開は `bash scripts/start.sh -d` を使用し、下記の起動後検証を行います。

#### 復元

復元元 `BACKUP_DIR` を選び、保存した commit・非秘密設定・Compose・Weaviate image と
保存先を確認します。バックアップの `.env` をシェルで `source` しないでください。
旧コードに戻す場合は記録された commit と対応する image を用意し、非秘密設定を復元します。
Bitwarden のシークレットは起動時に注入します。保存先を変更する場合は Compose の bind mount
も一致させてください。Weaviate データは保存時と同じバージョンで起動します。

再度、上記と同じ順で全サービスと手動更新処理を停止します。復元元は停止・確認後に指定します。

```bash
BACKUP_DIR='/backup/grimoire-keeper/backup-<保存時刻と識別子>'
sudo cat "$BACKUP_DIR/git-commit.txt" "$BACKUP_DIR/weaviate-image.txt" "$BACKUP_DIR/weaviate-data-path.txt"
# 確認した値を設定する（通常は保存時と同じ値）。
DATA_ROOT=/opt/grimoire-keeper-data
export WEAVIATE_DATA_PATH=/opt/grimoire-keeper-data/weaviate-1.38.8
export WEAVIATE_IMAGE=cr.weaviate.io/semitechnologies/weaviate:1.38.8
```

復元先は互いに重複しない実ディレクトリを指定し、バックアップ保存先を含めないでください。
十分な空き容量を確認します。以下は全データを一時ディレクトリに展開してから、既存データを
隣接する退避ディレクトリへ移動します。上書きコピーしないので古い JSON や WAL が残りません。
途中失敗時は起動せず、表示された退避先を保持して原因を解消し、3 種のデータを同じセットに
揃え直します。復元完了後も退避先とバックアップは検証が終わるまで保持します。

<!-- restore-files:start -->
```bash
case "$BACKUP_DIR" in *.partial) echo '未完了のバックアップです' >&2; exit 1;; esac
sudo test -f "$BACKUP_DIR/COMPLETE"
for name in database json migration weaviate; do
  sudo test -d "$BACKUP_DIR/$name"
done
sources=(database json migration weaviate)
targets=("$DATA_ROOT/database" "$DATA_ROOT/json" "$DATA_ROOT/migration" "$WEAVIATE_DATA_PATH")
stages=()
for i in "${!sources[@]}"; do
  target=${targets[$i]}
  test -n "$target" && test "$target" != /
  test ! -L "$target"
  sudo mkdir -p "$(dirname "$target")"
  stage=$(sudo mktemp -d "${target}.restore-XXXXXX")
  stages+=("$stage")
  sudo cp -a "$BACKUP_DIR/${sources[$i]}" "$stage/restored"
  printf '復元作業・既存データ退避先: %s\n' "$stage"
done
for i in "${!sources[@]}"; do
  target=${targets[$i]}
  stage=${stages[$i]}
  if sudo test -e "$target"; then
    sudo mv -T "$target" "$stage/previous"
  fi
  sudo mv -T "$stage/restored" "$target"
done
```
<!-- restore-files:end -->

起動前に所有権を確認します。現行アプリでは次を実行します。旧コードを復元する場合は、
そのバージョンの実行 UID/GID に合わせます。Weaviate は `cp -a` で保持した所有権を確認し、
アプリ用 UID へ一括変更しません。

```bash
sudo chown -R 10001:10001 "$DATA_ROOT/database" "$DATA_ROOT/json" "$DATA_ROOT/migration"
sudo chmod 0750 "$DATA_ROOT/database" "$DATA_ROOT/json" "$DATA_ROOT/migration"
sudo stat -c '%u:%g %a %n' "$DATA_ROOT/database" "$DATA_ROOT/database/grimoire.db" \
  "$DATA_ROOT/json" "$DATA_ROOT/migration" "$WEAVIATE_DATA_PATH"
# 記録したコードと設定を用意した後、対応するイメージで起動する。
bash scripts/start.sh -d --build
```

#### 起動後検証

```bash
docker compose -f docker-compose.prod.yml exec -T api python ../../scripts/init_database.py check
curl --fail http://localhost:8089/v1/.well-known/ready
curl --fail http://localhost:8001/api/v1/health
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 api worker weaviate
```

worker が healthy になるまで確認し、保存済みページの本文取得と代表的な検索を UI で確認します。
検証に失敗した場合は入口・API・worker を停止し、Weaviate も停止して原因を調べます。
SQLite・JSON・Weaviate の一部だけを別時点へ戻して運用を再開しないでください。

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
