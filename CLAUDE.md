# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) and Grok when working with code in this repository.

## プロジェクト概要

**atelier** — 画像/動画編集 webapp。

バックエンドは複数（Grok API / Stable Diffusion WebUI）。生成物を入力として再利用でき、依存関係をツリー状に可視化する。

### 機能（仕様）

| 機能 | 説明 | バックエンド |
|------|------|-------------|
| Text-to-Image | テキストから画像生成 | Grok / SD WebUI |
| Text-to-Video | テキストから動画生成 | Grok |
| Image-to-Image | 画像 + プロンプトで編集 | Grok / SD WebUI |
| Image-to-Video | 画像から動画生成 | Grok |
| 再利用 | アプリ上の生成物を次の入力に使える（バックエンド横断可） | — |
| ツリー表示 | どの入力から生成したかを可視化 | — |
| 複数入力 | `@Image1`, `@Image2` 形式で参照 | — |
| ダウンロード | 生成物の確認・保存 | — |

### 起動

```bash
uv run atelier start
# listen on 0.0.0.0 — ブラウザからアクセス
```

## 現状

- フェーズ 0–1 完了。
- パッケージ `atelier`、CLI、FastAPI、`MediaNode`/`Graph` 永続化、media API（list/get/file/upload）。
- 生成バックエンド・UI 本実装は未着手（TODO.md フェーズ 2 以降）。

## ディレクトリ構成

```
src/atelier/
  __init__.py      # version
  __main__.py      # python -m atelier
  cli.py           # argparse CLI (start)
  app.py           # FastAPI factory
  config.py        # pydantic-settings
  backends/        # Grok / SD WebUI (stub)
  graph/
    models.py      # MediaNode, Edge, Graph
    store.py       # graph.json persistence
  media/
    store.py       # files/ storage
  api/
    media.py       # /api/media/*
  static/          # frontend static files
tests/
  test_media_api.py
```

## 技術スタック

グローバル規約（`~/.grok/AGENTS.md`）に従う:

- **Python** >= 3.13
- **パッケージ管理**: `uv`
- **フォーマット**: `black --line-length 120`
- **型チェック**: `ty`
- **Web**: FastAPI + uvicorn

### バックエンド

| 名前 | 種別 | 認証 / 接続 | 担当 |
|------|------|-------------|------|
| Grok | クラウド API | `XAI_API_KEY` | 画像 + 動画 |
| SD WebUI | ローカル HTTP | `SD_WEBUI_URL`（例: `http://127.0.0.1:7860`） | 画像 (txt2img / img2img) |

#### Grok (xAI)

- `POST https://api.x.ai/v1/images/generations` — 生成
- `POST https://api.x.ai/v1/images/edits` — 編集
- model: `grok-imagine-image` 等

#### Stable Diffusion WebUI（将来）

- **本体は別プロセス**。atelier はクライアント。同梱しない。
- A1111 互換 API 必須: WebUI 起動時 `--api`
- 主要エンドポイント:
  - `POST /sdapi/v1/txt2img`
  - `POST /sdapi/v1/img2img`
  - `GET  /sdapi/v1/sd-models` — チェックポイント一覧
  - `POST /sdapi/v1/options` — モデル切替等
- 想定チェックポイント: **WAI-NSFW-illustrious-SDXL**
  - Civitai: https://civitai.com/models/827813/wai-nsfw-illustrious-sdxl
  - Illustrious 系 SDXL。Danbooru タグ向き。VRAM 8GB+ 目安
  - WebUI の `models/Stable-diffusion/` に配置（ユーザー側）
- UI で渡すパラメータ例: prompt / negative_prompt / steps / cfg_scale / width / height / sampler / seed / denoising_strength (img2img) / override_settings.sd_model_checkpoint
- Forge / reForge 等 A1111 互換 API があれば同じクライアントで接続可（将来）

### 設定（環境変数）

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `XAI_API_KEY` | (なし) | xAI API キー |
| `SD_WEBUI_URL` | `http://127.0.0.1:7860` | SD WebUI base URL |
| `ATELIER_HOST` | `0.0.0.0` | bind host |
| `ATELIER_PORT` | `8000` | bind port |
| `ATELIER_DATA_DIR` | `data` | 生成物・グラフ保存先 |
| `ATELIER_HTTP_TIMEOUT` | `60` | 通常 API タイムアウト秒 |
| `ATELIER_VIDEO_TIMEOUT` | `600` | 動画生成タイムアウト秒 |

### 関連実装（参考）

| リポジトリ | 用途 |
|-----------|------|
| `~/git/grok-mcp-server` | 画像生成/編集の xAI API 呼び出し例 |
| `~/git/grok-http-server` | FastAPI + Grok の HTTP サーバー構成 |

## 開発コマンド

```bash
uv sync                          # 依存関係
uv run atelier start             # サーバー起動
uv run black .                   # フォーマット (line-length 120)
uv run ty check                  # 型チェック
uv run pytest                    # テスト
```

## 設計上の注意

1. **生成グラフ**: 各生成結果はノード。入力参照（ユーザーアップロード / 過去生成）はエッジ。UI でツリー/DAG 表示。ノードにバックエンド種別をメタデータとして持つ。
2. **@参照**: プロンプト内の `@ImageN` / `@VideoN` を実際のメディアに解決して API に渡す。
3. **バックエンド抽象**: `Backend` インターフェース（generate / edit 等）。Grok と SD WebUI を差し替え。UI で実行時に選択。
4. **バックエンド横断**: 例: SD (WAI) で画像 → Grok で Image-to-Video。グラフ上は通常のエッジ。
5. **永続化**: 生成物・グラフは `ATELIER_DATA_DIR` 配下。セッションまたぎの再利用を想定。
6. **サーバー**: `0.0.0.0` で listen。`--host` / `--port` または環境変数で変更可。
7. **SD WebUI 障害**: 未起動・タイムアウト時はエラーを UI に返す。Grok 側は独立して動く。

## 実装方針

- 仕様は README を正とする。矛盾があれば README を更新してからコードを合わせる。
- パッケージ名 / CLI エントリ: `atelier`（`uv run atelier start`）。
- 依存は最小限。画像/動画処理と Web フレームワークのみ追加。SD WebUI 本体は依存に含めない。
- 型ヒント必須。docstring は日本語可。
- 実装優先度の目安: Grok 一通り → 生成グラフ/再利用 → SD WebUI (WAI-NSFW-illustrious-SDXL)。
