# Grimoire Keeper タスク管理

**最終更新**: 2024年12月  
**テスト状況**: 105 passed, 10 failed (91% 成功率)  
**プロジェクト状況**: 基本機能完成、セキュリティ・品質改善フェーズ

## 🔴 フェーズ1: セキュリティ・クリーンアップ (1-2日)

### 1. データ漏洩リスクの解消 ⚠️ 最優先
**工数**: 10分 | **ファイル**: git管理
```bash
git rm --cached grimoire.db apps/api/grimoire.db
git rm --cached data/json/*.json
git rm -r --cached .mypy_cache .ruff_cache
git commit -m "security: Remove sensitive data from repository"
```

### 2. セキュリティ脆弱性の修正 ⚠️
**工数**: 4-6時間 | **ファイル**: `apps/api/src/grimoire_api/main.py`, `config.py`
- [ ] CORS設定の厳格化 (環境変数 `ALLOWED_ORIGINS`)
- [ ] API Key認証の実装
- [ ] レート制限の追加 (`slowapi`: 100 req/min/IP)
- [ ] 入力値検証の強化

### 3. 環境変数の必須チェック
**工数**: 1-2時間 | **ファイル**: `apps/api/src/grimoire_api/config.py`
- [ ] 起動時バリデーション関数
- [ ] 必須変数リスト明示
- [ ] エラーメッセージ改善

### 4. ユニットテストの修正
**工数**: 2-3時間 | **ファイル**: `apps/api/tests/unit/`
- [ ] `test_search.py`: 3件 (ベクトル検索)
- [ ] `test_chunking_service.py`: 1件
- [ ] `test_llm_service.py`: 4件
- [ ] `test_vectorizer.py`: 2件

## 🟡 フェーズ2: 基盤強化 (3-5日)

### 5. 共有ライブラリの実装
**工数**: 1日 | **ファイル**: `shared/src/grimoire_shared/`
- [ ] 共通モデル (`models/page.py`, `models/search.py`)
- [ ] ユーティリティ関数 (`utils/validation.py`, `utils/datetime.py`)
- [ ] 設定管理の統一 (`config.py`)

### 6. エラーハンドリングの改善
**工数**: 1日 | **ファイル**: `apps/api/src/grimoire_api/utils/`
- [ ] カスタム例外拡充 (`DatabaseError`, `ExternalAPIError`)
- [ ] 構造化ログ導入 (`structlog`)
- [ ] 統一エラーレスポンスモデル

### 7. データベースインデックス追加
**工数**: 1時間 | **ファイル**: `scripts/add_indexes.sql`
```sql
CREATE INDEX idx_pages_url ON pages(url);
CREATE INDEX idx_pages_status ON pages(status);
CREATE INDEX idx_pages_created_at ON pages(created_at);
CREATE INDEX idx_logs_page_id ON processing_logs(page_id);
```

### 8. Bot型エラーの修正
**工数**: 2時間 | **ファイル**: `apps/bot/src/grimoire_bot/`
- [ ] slack-bolt型スタブ追加 or 型チェック除外
- [ ] 型アノテーション追加 (5件)

## 🟢 フェーズ3: 品質向上 (3-5日)

### 9. テスト環境の改善
**工数**: 半日 | **ファイル**: `apps/api/tests/conftest.py`
- [ ] `conftest_integration.py`の統合
- [ ] 共通モックフィクスチャ作成
- [ ] テストデータファクトリ実装

### 10. キャッシュ機能の実装
**工数**: 1日 | **ファイル**: `apps/api/src/grimoire_api/services/cache.py`
- [ ] インメモリキャッシュ (`cachetools`)
- [ ] 検索結果キャッシュ (TTL: 5分)
- [ ] Redis導入検討

### 11. pre-commitフックの設定
**工数**: 1時間 | **ファイル**: `.pre-commit-config.yaml`
- [ ] ruff, mypy, pytest自動実行
- [ ] コミット前品質チェック

### 12. OpenTelemetry依存の見直し
**工数**: 2時間 | **ファイル**: `shared/src/grimoire_shared/telemetry.py`
- [ ] オプショナル化
- [ ] 環境変数での有効/無効切り替え
- [ ] 開発環境デフォルト無効

## 🔵 フェーズ4: 自動化・拡張 (2週間以上)

### 13. CI/CDパイプライン構築
**工数**: 1-2日 | **ファイル**: `.github/workflows/`
- [ ] テスト自動実行
- [ ] Dockerイメージビルド
- [ ] 自動デプロイ

### 14. Slackボット実装
**工数**: 3-5日 | **ファイル**: `apps/bot/src/grimoire_bot/handlers/`
- [ ] イベントハンドラー実装
- [ ] コマンド処理実装
- [ ] バックエンドAPI連携

### 15. ドキュメント整理
**工数**: 半日 | **ファイル**: `SETUP.md`, `docs/`
- [ ] セットアップガイド統合
- [ ] API仕様書更新
- [ ] 実装との整合性チェック

## 📊 進捗サマリー

### ✅ 完了 (7項目)
- Weaviate v4 API対応
- ruff コード品質チェック
- 主要サービス実装 (URL処理、検索、ベクトル化)
- 統合テスト修正
- データベース初期化自動化
- API型エラー修正 (mypy)
- 警告解消

### 🔄 進行中 (15項目)
- フェーズ1: 4項目 (セキュリティ、データ漏洩、環境変数、テスト)
- フェーズ2: 4項目 (共有ライブラリ、エラーハンドリング、DB、Bot型)
- フェーズ3: 4項目 (テスト改善、キャッシュ、pre-commit、OTel)
- フェーズ4: 3項目 (CI/CD、Slackボット、ドキュメント)

### 📈 全体進捗
- **完了**: 7/22 (32%)
- **残タスク**: 15/22 (68%)
- **推定工数**: 10-15日

## 🎯 今週の目標

### 今日やること
- [ ] データ漏洩リスク解消 (10分)
- [ ] セキュリティ修正開始 (CORS設定)

### 今週中に完了
- [ ] フェーズ1完了 (セキュリティ・クリーンアップ)
- [ ] ユニットテスト10件修正
- [ ] 環境変数検証実装

## 📝 参考情報

### 技術的負債
- データベーススキーマの正規化
- 設定管理の統一化
- ログ機能の標準化 (print → logging)
- OpenTelemetry依存の強制

### 既知の問題
- テスト警告90件 (抑制済み、根本解決必要)
- OpenTelemetry接続エラー (開発環境で不要)
- `tool.uv.dev-dependencies`非推奨警告

### 将来的な拡張
- 複数ユーザー対応
- ファイルアップロード機能
- 検索ランキング改善
- リアルタイム通知
- GraphQL API

---

**最終更新**: 2024年12月 | **更新者**: Amazon Q | **次回レビュー**: フェーズ1完了後