#!/usr/bin/env python3
"""サービス状態チェックスクリプト."""

import asyncio
import sys
from pathlib import Path

import httpx

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "apps" / "api" / "src"))

from grimoire_api.config import settings


async def check_weaviate():
    """Weaviate接続チェック."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.WEAVIATE_URL}/v1/meta", timeout=5.0)
            if response.status_code == 200:
                print("✅ Weaviate: 接続OK")
                return True
            else:
                print(f"❌ Weaviate: HTTP {response.status_code}")
                return False
    except Exception as e:
        print(f"❌ Weaviate: 接続失敗 - {e}")
        return False


async def check_api():
    """API接続チェック."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/api/v1/health", timeout=5.0)
            if response.status_code == 200:
                print("✅ API: 接続OK")
                return True
            else:
                print(f"❌ API: HTTP {response.status_code}")
                return False
    except Exception as e:
        print(f"❌ API: 接続失敗 - {e}")
        return False


def check_env_vars():
    """環境変数チェック."""
    required_vars = ["OPENAI_API_KEY", "GOOGLE_API_KEY", "JINA_API_KEY"]
    missing_vars = []
    
    for var in required_vars:
        value = getattr(settings, var, "")
        if not value or value == "":
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ 環境変数: 未設定 - {', '.join(missing_vars)}")
        return False
    else:
        print("✅ 環境変数: 設定OK")
        return True


def check_database():
    """データベースファイルチェック."""
    db_path = Path(settings.DATABASE_PATH)
    if db_path.exists():
        print("✅ データベース: ファイル存在")
        return True
    else:
        print("❌ データベース: ファイル未作成")
        return False


async def main():
    """メイン処理."""
    print("🔍 サービス状態をチェックしています...\n")
    
    checks = [
        ("環境変数", check_env_vars()),
        ("データベース", check_database()),
        ("Weaviate", await check_weaviate()),
        ("API", await check_api()),
    ]
    
    all_ok = True
    for name, result in checks:
        if not result:
            all_ok = False
    
    print("\n" + "="*50)
    if all_ok:
        print("🎉 全てのサービスが正常に動作しています!")
    else:
        print("⚠️  一部のサービスに問題があります。")
        print("詳細は SETUP_API.md を確認してください。")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())