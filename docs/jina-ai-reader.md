# Jina AI Reader API 仕様

## 概要
Jina AI ReaderはURLからコンテンツを取得し、Markdown形式で構造化されたデータとして返すAPIサービスです。HTMLパースは不要で、直接Markdownコンテンツを取得できます。

## リクエスト仕様

### エンドポイント
```
GET https://r.jina.ai/{target_url}
```

### ヘッダー
```http
Accept: application/json
Authorization: Bearer {jina_api_key}
X-Return-Format: markdown
X-With-Images-Summary: true
```

### リクエスト例
```bash
curl "https://r.jina.ai/https://example.com/article" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer jina_API_KEY" \
  -H "X-Return-Format: markdown" \
  -H "X-With-Images-Summary: true"
```

## レスポンス仕様

### 成功レスポンス (200 OK)
```json
{
  "code": 200,
  "status": 20000,
  "data": {
    "images": {},
    "title": "記事のタイトル",
    "description": "記事の概要説明文",
    "url": "https://example.com/article",
    "content": "記事の本文内容（Markdown形式）",
    "publishedTime": "Mon, 01 Jan 2024 12:00:00 GMT",
    "metadata": {
      "viewport": "width=device-width, initial-scale=1",
      "og:site_name": "サイト名",
      "og:type": "article",
      "og:image": "https://example.com/image.jpg",
      "twitter:image": "https://example.com/image.jpg",
      "title": "ページタイトル",
      "og:title": "OGタイトル",
      "twitter:title": "Twitterタイトル",
      "description": "ページ説明文",
      "og:description": "OG説明文",
      "twitter:description": "Twitter説明文",
      "twitter:card": "summary",
      "keyword": "キーワード1 キーワード2"
    },
    "external": {
      "icon": {
        "https://example.com/favicon.ico": {}
      },
      "canonical": {
        "https://example.com/article": {}
      }
    },
    "usage": {
      "tokens": 1500
    }
  },
  "meta": {
    "usage": {
      "tokens": 1500
    }
  }
}
```

### 主要フィールド説明

| フィールド | 型 | 説明 |
|-----------|----|----|
| `data.title` | string | ページのタイトル |
| `data.description` | string | ページの概要 |
| `data.url` | string | 取得対象のURL |
| `data.content` | string | ページの本文（Markdown形式、直接利用可能） |
| `data.publishedTime` | string | 公開日時（RFC 2822形式） |
| `data.metadata` | object | メタデータ（OG、Twitter Card等） |
| `data.images` | object | 画像情報 |
| `data.external` | object | 外部リソース情報 |
| `data.usage.tokens` | number | 使用トークン数 |

## エラーレスポンス

### 4xx/5xx エラー
```json
{
  "code": 400,
  "status": 40000,
  "message": "エラーメッセージ"
}
```

## 使用上の注意

### レート制限
- APIキーごとに月間制限あり
- 詳細は Jina AI の料金プランを参照

### コンテンツ制限
- 一部のサイトはアクセス制限により取得不可
- 動的コンテンツ（JavaScript必須）は取得困難な場合あり

### トークン消費
- `data.usage.tokens` でトークン消費量を確認可能
- 長いページほど多くのトークンを消費