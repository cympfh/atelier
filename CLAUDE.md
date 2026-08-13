# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) and Grok when working with code in this repository.

## プロジェクト概要

**atelier** — 画像/動画編集 webapp。

- 複数バックエンド（Grok / SD WebUI / Echo）
- 生成 lineage（DAG）の可視化・名前付き保存
- 生成物の入力再利用・Restore setup

### 起動

```bash
uv run atelier start
# http://127.0.0.1:8000/
```

---

## 実装済み機能

### コア

| 領域 | 内容 |
|------|------|
| CLI | `atelier start`（`--host` / `--port` / `--reload`） |
| 設定 | pydantic-settings + 環境変数 |
| Media | アップロード・一覧・本体配信・**葉ノード削除** |
| Graph | nodes + edges、`data/lineages/{id}/` に永続化 |
| Lineage | 名前付きワークスペース、切替・改名・10秒 autosave |
| Generate | 同期 / 非同期 JobQueue（video は自動 async） |
| @参照 | `@ImageN` / `@VideoN` → `input_slots` または候補から解決 |
| SPA UI | Compose / Preview / Gallery / Lineage |

### バックエンド

| 名前 | 能力 |
|------|------|
| **grok** | T2I / I2I（最大3枚）/ T2V / I2V / **video edit**（動画入力） |
| **sd_webui** | T2I / I2I、LoRA・clip_skip・hires・alwayson_scripts |
| **echo** | オフライン用ダミー（`ATELIER_ECHO=1`） |

### UI の mode 自動判定

ユーザーが選ぶのは **→ Image / → Video** のみ（radio）。

| Output | Input slots | 実 mode |
|--------|-------------|---------|
| Image | 空 | t2i |
| Image | あり | i2i |
| Video | 空 | t2v |
| Video | 画像 | i2v（animate） |
| Video | 動画 | **v2v**（Grok video edit） |

- **→ Image** では動画を slot に入れない（Use as input 非表示・switch 時 prune）
- **→ Video** では画像・動画どちらも入力可

### Preview アクション

| ボタン | 色 | 動作 |
|--------|-----|------|
| Download | ティール | ファイル DL |
| Use as input | アンバー | slot に追加（制約あり） |
| Restore setup | 青紫 | 生成時 prompt / parents / params / backend 復元 |
| Delete | 赤 | **葉のみ**削除（非葉は disabled + API 409） |

### 主要 API

| Method | Path | 説明 |
|--------|------|------|
| GET/POST | `/api/media`, `/upload`, `/{id}`, `/{id}/file` | media CRUD |
| DELETE | `/api/media/{id}` | 葉のみ。非葉は 409 `not_a_leaf` |
| POST | `/api/generate` | 生成（`async_job` / video で job） |
| GET | `/api/jobs`, `/api/jobs/{id}` | ジョブ poll |
| GET | `/api/backends` | 能力 + `param_schema` |
| GET | `/api/graph` | nodes + edges |
| * | `/api/lineages*` | lineage 一覧・切替・改名・save |
| GET | `/api/sd/models` | SD チェックポイント |

### データ配置

```
{ATELIER_DATA_DIR}/
  lineages/
    active.json
    {lineage_id}/
      meta.json      # name, timestamps
      graph.json     # nodes + edges
      files/         # {id}.ext
  .migrated_to_lineages  # 旧 data/graph.json 移行済みマーカー
```

---

## ディレクトリ構成

```
src/atelier/
  cli.py app.py config.py
  refs.py jobs.py lineage.py
  backends/
    base.py types.py registry.py pipeline.py
    grok_client.py grok.py
    sd_webui.py echo.py
  graph/models.py store.py
  media/store.py
  api/media.py generate.py lineages.py
  static/                 # SPA + favicon
    index.html app.js app.css
    icons/ favicon.ico
icons/                    # 源 SVG と raster 生成物
tests/
```

---

## 開発スタイル

グローバル（`~/.grok/AGENTS.md`）に従う:

- **Python >= 3.13**
- **uv** で依存・実行
- **black --line-length 120**
- **ty check** で型
- 型ヒント必須。docstring は日本語可

### 方針

1. **仕様は README / この CLAUDE.md を正**。矛盾したら docs を先に直す
2. **Backend 抽象**を壊さない。新プロバイダは `Backend` 実装 + registry 登録
3. **依存最小**。SD WebUI 本体は同梱しない
4. **静的 UI** は `static/` の単一 SPA。変更時は `index.html` の `?v=N` を上げてキャッシュ回避
5. テストは **httpx MockTransport** で外部 API をモック。echo で E2E パイプライン
6. 1 機能まとまりごとに commit しやすい粒度を意識

### 開発コマンド

```bash
uv sync
uv run atelier start --reload
uv run black .
uv run ty check
uv run pytest
```

---

## 注意点・落とし穴

### xAI Grok

1. **I2I の `image` は文字列**（URL / data URI）。`{"url","type"}` map は 422  
   - 複数枚: `image: ["data:...", "data:..."]`（最大 3）
2. **動画入力は Image-to-Video ではなく Video Edit**  
   - **エンドポイントは `POST /v1/videos/edits`**（`/videos/generations` ではない）  
   - body: `video: {url: data URI or public URL}`。duration/aspect は source 継承  
   - `/generations` に `video` を載せても無視され、prompt だけの T2V になる（エラーにならない）
3. **動画生成は async** — generations/edits とも `request_id` → `GET /v1/videos/{id}` poll  
   - アプリ側 JobQueue も video mode で自動 async
4. **動画の `n`** は API 一括ではなく **直列リクエスト**（`grok.py`）
5. models: `grok-imagine-image-quality`, `grok-imagine-video-1.5`（edit の docs 例は `grok-imagine-video` のことも）

### グラフ・削除

6. **Delete は葉のみ** — 子があるノードは削除不可（API 409 / UI disabled）  
   - 子を先に消す必要あり
7. lineage 切替後は `app.state.graph_store` / `media_store` / JobQueue を **sync** する（`sync_active_stores`）

### UI

8. ブラウザキャッシュで古い `app.js` が残ると radio 化後に `outSel.options` エラー等が出る → **`?v=` を必ず bump**
9. ノードの prompt は `@ImageN` を **保持**（backend 送信時のみ strip）。Restore setup は prompt + `parent_ids` から復元
10. 大画像 upload は **クライアントで長辺 2048 にリサイズ**（gif はそのまま）

### SD WebUI

11. 未起動時は `available: false`。Grok は独立して動く
12. LoRA は `lora: "name:0.8,other:0.5"` → prompt 末尾に `<lora:...>` を付与

### エラー形式

13. API エラーは多くが `detail: { "error": "<code>", "detail": "..." }`  
    - 例: `backend_unavailable`, `not_a_leaf`, `mode_not_supported`

---

## 環境変数

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `XAI_API_KEY` | — | Grok |
| `SD_WEBUI_URL` | `http://127.0.0.1:7860` | SD WebUI |
| `ATELIER_HOST` / `PORT` | `0.0.0.0` / `8000` | bind |
| `ATELIER_DATA_DIR` | `data` | lineage ルート |
| `ATELIER_HTTP_TIMEOUT` | `60` | 秒 |
| `ATELIER_VIDEO_TIMEOUT` | `600` | 秒 |
| `ATELIER_ECHO` | `false` | echo backend |

---

## 関連リポジトリ

| path | 用途 |
|------|------|
| `~/git/grok-mcp-server` | xAI 画像 API の先行実装例 |
| `~/git/grok-http-server` | FastAPI + Grok HTTP 構成例 |
