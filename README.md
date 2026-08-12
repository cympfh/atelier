# atelier

画像/動画編集 webapp（Grok + Stable Diffusion WebUI）

生成物を入力として再利用し、依存関係をツリー（lineage）で可視化する。

## 機能

- **Grok** (xAI Imagine API)
  - Text-to-Image / Image-to-Image / Text-to-Video / Image-to-Video
- **Stable Diffusion WebUI** (A1111 互換 API、別プロセス)
  - Text-to-Image / Image-to-Image
  - 想定モデル: [WAI-NSFW-illustrious-SDXL](https://civitai.com/models/827813/wai-nsfw-illustrious-sdxl)
- アップロード・ギャラリー・ダウンロード
- `@Image1` / `@Video1` による入力参照
- 生成 lineage（グラフ）表示

## セットアップ

```bash
uv sync   # Python >= 3.13

export XAI_API_KEY="..."                          # Grok 用
export SD_WEBUI_URL="http://127.0.0.1:7860"       # SD WebUI（任意）
export ATELIER_HOST="0.0.0.0"
export ATELIER_PORT="8000"
export ATELIER_DATA_DIR="data"
export ATELIER_ECHO=1                             # オフライン用 echo バックエンド（任意）
```

## 起動

```bash
uv run atelier start
# uv run atelier start --host 0.0.0.0 --port 8000 --reload
```

ブラウザ: `http://127.0.0.1:8000/`

### SD WebUI（任意）

1. AUTOMATIC1111 / Forge 等を `--api` 付きで起動
2. チェックポイントを `models/Stable-diffusion/` に配置（例: WAI-NSFW-illustrious-SDXL）
3. `SD_WEBUI_URL` を設定して atelier を起動
4. UI の backend で `sd_webui` を選択。checkpoint パラメータにモデル title を指定可

推奨の目安（Illustrious / SDXL）: 1024×1024、sampler `Euler a`、steps 28 前後。

## API 概要

| Method | Path | 説明 |
|--------|------|------|
| GET | `/health` | ヘルス |
| GET | `/api/backends` | バックエンド一覧 + 能力 + param_schema |
| GET | `/api/media` | メディア一覧 |
| GET | `/api/media/{id}` | メタデータ |
| GET | `/api/media/{id}/file` | 本体 |
| POST | `/api/media/upload` | アップロード (`file`) |
| POST | `/api/generate` | 生成ジョブ |
| GET | `/api/graph` | ノード + エッジ |
| GET | `/api/sd/models` | SD チェックポイント一覧 |

### `POST /api/generate`

```json
{
  "mode": "t2i",
  "backend": "grok",
  "prompt": "a cat, @Image1 style",
  "media_ids": ["..."],
  "input_slots": ["..."],
  "params": { "aspect_ratio": "1:1" },
  "resolve_at_refs": true
}
```

## 開発

```bash
uv run black .
uv run ty check
uv run pytest
```

## 手動 E2E チェックリスト

- [ ] Grok T2I / I2I / T2V / I2V（`XAI_API_KEY` 必要）
- [ ] アップロード → ギャラリー → ダウンロード
- [ ] 入力スロット + `@Image1` 参照
- [ ] Lineage ツリー表示・クリックでプレビュー
- [ ] SD T2I / I2I（WebUI `--api` + モデル）
- [ ] SD 生成 → Grok I2V など横断再利用
- [ ] キー無し / SD ダウン時のエラー表示
