# devcontainer内でのAmazon Q使用方法

## 前提条件

1. **ホストマシンでAWS認証設定済み**
   ```bash
   # AWS CLIまたはAWS Toolkitで認証済み
   aws configure list
   ```

2. **Amazon Q拡張機能がインストール済み**
   - devcontainer起動時に自動インストール

## 使用方法

### 1. 認証確認
```bash
# devcontainer内で確認
ls -la ~/.aws/
cat ~/.aws/config
```

### 2. Amazon Q機能
- **チャット**: `Ctrl+Shift+P` → "Amazon Q: Open Chat"
- **インライン補完**: 自動で有効
- **コード説明**: コード選択 → 右クリック → "Amazon Q: Explain"

### 3. プロジェクトルール活用
```bash
# プロジェクトルールが自動適用
@workspace での質問で技術スタック情報を参照

# 保存プロンプト使用
@prompt setup-devcontainer
@prompt python-monorepo
```

## トラブルシューティング

### 認証エラーの場合
1. ホストマシンで `aws configure` 再実行
2. devcontainer再起動
3. VSCodeでAmazon Q拡張機能の再認証