# atelier

画像/動画編集 webapp（Grok + Stable Diffusion WebUI）

## 概要

- Python 製
- `uv run atelier start`
    - server が起動 (listen on 0.0.0.0)
    - web ブラウザでアクセス可能
- 複数バックエンドで画像/動画編集が可能
    - **Grok** (xAI API)
        - Text-to-Image / Text-to-Video / Image-to-Image / Image-to-Video
    - **Stable Diffusion WebUI** (ローカル, 将来)
        - Text-to-Image / Image-to-Image
        - 想定モデル: [WAI-NSFW-illustrious-SDXL](https://civitai.com/models/827813/wai-nsfw-illustrious-sdxl)
        - A1111 互換 API (`--api`) 経由で接続（WebUI 本体は別プロセス）
- 自分で入力を用意する以外に、このアプリ上で生成した画像/動画を入力として再利用可能
    - どの入力を使ったかをツリー状に表示することで、生成の過程を可視化
    - バックエンドをまたいだ再利用も想定（例: SD で生成 → Grok で動画化）
- 入力が複数あっても `@Image1, @Image2` のように指定可能
- 生成された画像/動画は、アプリ上で確認できるだけでなく、ダウンロードも可能

## セットアップ

```bash
# 依存関係（Python >= 3.13）
uv sync

# 環境変数（任意）
export XAI_API_KEY="..."
export SD_WEBUI_URL="http://127.0.0.1:7860"   # デフォルト
export ATELIER_HOST="0.0.0.0"                 # デフォルト
export ATELIER_PORT="8000"                    # デフォルト
export ATELIER_DATA_DIR="data"                # デフォルト
```

## 起動

```bash
uv run atelier start
# または
uv run atelier start --host 0.0.0.0 --port 8000

# 開発用オートリロード
uv run atelier start --reload
```

ブラウザで `http://127.0.0.1:8000/` 、ヘルスチェックは `http://127.0.0.1:8000/health`。

## 開発

```bash
# フォーマット (line-length 120)
uv run black .

# 型チェック
uv run ty check

# テスト
uv run pytest
```
