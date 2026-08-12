@CLAUDE TODO List

# フェーズ 0: プロジェクト骨格

## [x] プロジェクトを atelier にリネーム [2026-08-12 18:26 完了]
リポジトリ名・表示名・ドキュメント上の `igroktable` / `igrok-table` を **atelier** に統一する。対象: README.md、CLAUDE.md、TODO.md 内の旧名・説明文、GitHub リモート（`gh repo rename` 等、可能なら）、ディレクトリ名 `~/git/igroktable` → `~/git/atelier`（ユーザー確認のうえ）。以降のパッケージ名 / CLI は `atelier` 前提。
変更: GitHub `cympfh/igroktable` → `cympfh/atelier`、origin 更新。ローカルパス `~/git/igroktable` はセッション中のため未移動（任意で `mv ~/git/igroktable ~/git/atelier`）。

## [x] uv プロジェクト初期化 [2026-08-12 18:26 完了]
`pyproject.toml` 作成。パッケージ名 `atelier`。Python >= 3.13。エントリポイント `atelier = atelier.cli:main`。`uv sync` 済み。

## [x] パッケージディレクトリ構成 [2026-08-12 18:26 完了]
`src/atelier/` に `__init__.py`、`__main__.py`、`cli.py`、`app.py`、`config.py`、`backends/`、`graph/`、`media/`、`api/`、`static/` を配置。

## [x] 設定モジュール [2026-08-12 18:26 完了]
`config.py`：pydantic-settings。`XAI_API_KEY`、`SD_WEBUI_URL`、`ATELIER_HOST`/`PORT`/`DATA_DIR`/`HTTP_TIMEOUT`/`VIDEO_TIMEOUT`。

## [x] CLI: `atelier start` [2026-08-12 18:26 完了]
`uv run atelier start` で Web サーバー起動。`--host` / `--port` / `--reload` オプション。

## [x] Web フレームワーク選定と最小 HTTP サーバー [2026-08-12 18:26 完了]
FastAPI + uvicorn。`/`（index.html）、`/health`、`/static` マウント。

## [x] 開発ツール配線 [2026-08-12 18:26 完了]
black (line-length 120)、ty、pytest を uv dev 依存に追加。README に実行方法記載。`uv run black .` / `uv run ty check` 通過。

---

# フェーズ 1: ドメインモデルと永続化

## [x] メディアノード型定義 [2026-08-12 18:29 完了]
`graph/models.py`: `MediaNode`（id, kind, filename, mime, created_at, backend, prompt, params, parent_ids, original_name）。

## [x] 生成エッジ / グラフ型定義 [2026-08-12 18:29 完了]
`Edge`（source→target, role）、`Graph`（nodes dict + edges list）。JSON シリアライズ可。

## [x] ローカルメディア保存 [2026-08-12 18:29 完了]
`media/store.py`: `MediaStore` — `data/files/{id}.{ext}` に保存。mime から kind/ext 決定。

## [x] グラフ永続化 [2026-08-12 18:29 完了]
`graph/store.py`: `GraphStore` — `data/graph.json` に atomic write。再起動後も読込。

## [x] メディア一覧・取得 API [2026-08-12 18:29 完了]
`GET /api/media`、`GET /api/media/{id}`、`GET /api/media/{id}/file`。

## [x] アップロード API [2026-08-12 18:29 完了]
`POST /api/media/upload`（multipart）。backend=`upload` でグラフに追加。テスト 5 件通過。

---

# フェーズ 2: バックエンド抽象

## [x] Backend プロトコル / 抽象基底 [2026-08-12 18:33 完了]
`backends/base.py`: `Backend` ABC（`capabilities` / `availability` / `generate`）。能力フラグは `BackendCapabilities`。

## [x] バックエンドレジストリ [2026-08-12 18:33 完了]
`BackendRegistry` + `build_default_registry`（grok / sd_webui stubs、任意で echo）。app.state に配線。

## [x] 生成ジョブリクエスト型 [2026-08-12 18:33 完了]
`GenerateMode` / `GenerateRequest` / `MediaInput` / `GeneratedAsset` / 構造化エラー群（`backends/types.py`）。

## [x] 生成ジョブ実行パイプライン [2026-08-12 18:33 完了]
`run_generate`: media 解決 → 検証 → backend.generate → save + graph。EchoBackend でテスト 11 件。

---

# フェーズ 3: Grok バックエンド

## [x] Grok クライアント基盤 [2026-08-12 18:38 完了]
`backends/grok_client.py`: httpx、認証、画像/動画ダウンロード、動画ポーリング。

## [x] Grok Text-to-Image [2026-08-12 18:38 完了]
`POST /v1/images/generations`（`grok-imagine-image-quality`）。URL/b64 両対応。

## [x] Grok Image-to-Image [2026-08-12 18:38 完了]
`POST /v1/images/edits`。data URI、最大 3 枚。

## [x] Grok Text-to-Video [2026-08-12 18:38 完了]
`POST /v1/videos/generations` + poll `GET /v1/videos/{id}`。`video_timeout` 対応。

## [x] Grok Image-to-Video [2026-08-12 18:38 完了]
image data URI + prompt → 動画。

## [x] Grok パラメータ UI 向けスキーマ [2026-08-12 18:38 完了]
`GROK_PARAM_SCHEMA`（aspect_ratio, n, models, duration, resolution）を `/api/backends` 経由で露出。

## [x] Grok バックエンド単体テスト / 手動確認手順 [2026-08-12 18:38 完了]
`tests/test_grok.py`（MockTransport）。README に E2E チェックリスト。キー無しは 503。

---

# フェーズ 4: 生成 API（サーバー側）

## [x] `POST /api/generate` エンドポイント [2026-08-12 18:38 完了]
mode/backend/prompt/media_ids/params。同期で nodes 返却。

## [x] 生成進捗・長時間ジョブ対応（必要なら） [2026-08-12 18:38 完了]
動画 mode / `async_job` で JobQueue 非同期。xAI 動画はクライアント内ポーリング + `ATELIER_VIDEO_TIMEOUT`。

## [x] バックエンド一覧 API [2026-08-12 18:38 完了]
`GET /api/backends` + capabilities + param_schema。

## [x] エラーレスポンス統一 [2026-08-12 18:38 完了]
`AtelierError` → HTTP detail `{error, detail}`。

---

# フェーズ 5: @参照

## [x] プロンプト内 `@ImageN` / `@VideoN` パーサ [2026-08-12 18:38 完了]
`refs.py`: `parse_refs` / `strip_refs`。

## [x] 参照解決 [2026-08-12 18:38 完了]
`input_slots` 位置 or candidates。範囲外は InvalidRequestError。

## [x] 複数入力の Backend への受け渡し [2026-08-12 18:38 完了]
media_ids 順で MediaInput 化。プロンプトから @ トークン除去。Grok は最大 3 枚。

## [x] UI での入力スロット表示 [2026-08-12 18:38 完了]
ギャラリー double-click / Use as input。@ImageN ラベル表示。

---

# フェーズ 6: Web UI（コア）

## [x] フロントエンド基盤 [2026-08-12 18:38 完了]
`static/index.html` + `app.js` + `app.css`。

## [x] プロンプト入力 UI [2026-08-12 18:38 完了]
backend/mode 選択。非対応 mode は disabled。

## [x] パラメータパネル [2026-08-12 18:38 完了]
param_schema から動的生成。

## [x] メディアギャラリー [2026-08-12 18:38 完了]
サムネ一覧、選択、backend バッジ。

## [x] プレビュー表示 [2026-08-12 18:38 完了]
画像/動画プレビュー + メタデータ。

## [x] 生成実行ボタンとローディング [2026-08-12 18:38 完了]
Generate 中 disabled、エラー表示、成功時 refresh。

## [x] アップロード UI [2026-08-12 18:38 完了]
ファイル選択 → `/api/media/upload`。

## [x] ダウンロード [2026-08-12 18:38 完了]
プレビューの Download リンク。

---

# フェーズ 7: 生成ツリー可視化

## [x] グラフ取得 API [2026-08-12 18:38 完了]
`GET /api/graph`。

## [x] ツリー / DAG ビュー UI [2026-08-12 18:38 完了]
Lineage パネル。親子インデント。クリックでプレビュー。

## [x] ノードメタデータ表示 [2026-08-12 18:38 完了]
backend / kind / prompt 抜粋。プレビューに詳細。

## [x] バックエンド横断エッジの表示 [2026-08-12 18:38 完了]
backend 別色バッジ（grok / sd_webui / upload / echo）。

---

# フェーズ 8: SD WebUI バックエンド

## [x] SD WebUI HTTP クライアント [2026-08-12 18:38 完了]
`sd_webui.py`。availability で sd-models プローブ。

## [x] モデル一覧取得 [2026-08-12 18:38 完了]
`GET /api/sd/models` → WebUI sd-models。

## [x] モデル切替 [2026-08-12 18:38 完了]
`set_checkpoint` + generate 時 `override_settings.sd_model_checkpoint`。

## [x] SD Text-to-Image [2026-08-12 18:38 完了]
txt2img。モックテスト付き。

## [x] SD Image-to-Image [2026-08-12 18:38 完了]
img2img + denoising_strength。

## [x] SD パラメータ UI 向けスキーマ [2026-08-12 18:38 完了]
`SD_PARAM_SCHEMA` を backends API で露出。

## [x] SD 障害時の UX [2026-08-12 18:38 完了]
unavailable 表示。Grok は独立。

## [x] WAI-NSFW-illustrious-SDXL 動作確認手順 [2026-08-12 18:38 完了]
README に手順・推奨設定。

## [x] SD バックエンドとグラフ連携確認 [2026-08-12 18:38 完了]
パイプライン共通のため graph に載る。E2E は README チェックリスト。

---

# フェーズ 9: 仕上げ・品質

## [x] README を実装に合わせて更新 [2026-08-12 18:38 完了]
インストール・API・SD・E2E チェックリスト。

## [x] CLAUDE.md を実装構造に合わせて更新 [2026-08-12 18:38 完了]
構成・API・環境変数を現状反映。

## [x] 型チェック・フォーマット通過 [2026-08-12 18:38 完了]
black / ty クリーン。pytest 33 passed。

## [x] 基本の自動テスト [2026-08-12 18:38 完了]
refs / media / backends / grok mock / sd mock / generate API。

## [x] 手動 E2E チェックリスト [2026-08-12 18:38 完了]
README に記載。

## [x] エラー・エッジケース [2026-08-12 18:38 完了]
空プロンプト・未対応 mode・キー無し・不正 media id をテスト/検証。

## [x] （任意）非同期ジョブキュー [2026-08-12 18:45 完了]
`jobs.py` JobQueue。`POST /api/generate` の `async_job` または video mode で即 `job_id` 返却。`GET /api/jobs` / `GET /api/jobs/{id}` ポーリング。UI も poll 対応。

## [x] （任意）LoRA / 拡張 SD パラメータ [2026-08-12 18:45 完了]
`lora`（name:weight → `<lora:>`）、clip_skip、restore_faces、hires fix、alwayson_scripts JSON。テストで payload 検証。

## [x] 要望 [2026-08-12 18:48 完了]

- Prompt は Ctrl+Enter で Generate 送信する → 実装
- lineage 名前付き保存/一覧/切替 → `lineage.py` + `/api/lineages*` + ヘッダー UI
- 未保存時は `YYYY-MM-DD_HH-MM-SS` で自動作成
- 10秒おき `POST /api/lineages/current/save` で graph + meta を flush
- 各 lineage は `data/lineages/{id}/{graph.json,files/,meta.json}` にノード・メディア・prompt 等を保持

## [x] 要望 [2026-08-12 18:52 完了]

- Upload ボタンの代わりに D&D 領域「ここに画像を D&D」（クリック選択可）
- 長辺 > 2048 の画像は canvas でリサイズしてから upload
- Output は「→ Image / → Video」のみ。slot 有無で t2i/i2i/t2v/i2v を自動判定（mode hint 表示）
