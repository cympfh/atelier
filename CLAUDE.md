# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) and Grok when working with code in this repository.

## プロジェクト概要

**atelier** — 画像/動画編集 webapp。

バックエンド: Grok (xAI Imagine) / Stable Diffusion WebUI (A1111 API) / Echo (dev)。
生成物の再利用と lineage（生成グラフ）可視化。

### 起動

```bash
uv run atelier start
```

## 現状

フェーズ 0–9 実装済み（任意: JobQueue 非同期・SD LoRA/alwayson_scripts 含む）。

## ディレクトリ構成

```
src/atelier/
  cli.py / app.py / config.py
  refs.py                 # @ImageN / @VideoN
  jobs.py                 # async JobQueue
  backends/
    base.py registry.py pipeline.py types.py
    grok_client.py grok.py
    sd_webui.py echo.py   # LoRA / hires / alwayson_scripts
  graph/models.py store.py
  media/store.py
  api/media.py generate.py  # + /api/jobs
  static/                 # SPA (index.html app.js app.css)
tests/
```

## 技術スタック

- Python >= 3.13, uv, black (120), ty, pytest
- FastAPI + uvicorn + httpx + pydantic-settings

### 環境変数

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `XAI_API_KEY` | — | Grok |
| `SD_WEBUI_URL` | `http://127.0.0.1:7860` | SD WebUI |
| `ATELIER_HOST` / `PORT` | `0.0.0.0` / `8000` | bind |
| `ATELIER_DATA_DIR` | `data` | files/ + graph.json |
| `ATELIER_HTTP_TIMEOUT` | `60` | 秒 |
| `ATELIER_VIDEO_TIMEOUT` | `600` | 秒 |
| `ATELIER_ECHO` | `false` | echo backend |

### Grok API

- `POST /v1/images/generations` — T2I
- `POST /v1/images/edits` — I2I（最大 3 枚）
- `POST /v1/videos/generations` + `GET /v1/videos/{id}` — T2V/I2V（ポーリング）
- models: `grok-imagine-image-quality`, `grok-imagine-video-1.5`

### SD WebUI API

- `POST /sdapi/v1/txt2img`, `/img2img`
- `GET /sdapi/v1/sd-models`, `POST /sdapi/v1/options`
- 本体は同梱しない。`--api` 必須。

## 設計

1. `run_generate`: 入力解決 → Backend.generate → MediaStore + GraphStore
2. `@ImageN` は `input_slots` 位置、または候補リストで解決。プロンプトからトークン除去
3. ノードに `backend` / `params.mode` を保持し UI で色分け
4. エラーは `AtelierError.code` → HTTP JSON `detail: {error, detail}`

## 開発コマンド

```bash
uv sync
uv run atelier start
uv run black .
uv run ty check
uv run pytest
```
