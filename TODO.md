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

## [ ] Backend プロトコル / 抽象基底
`generate_image`、`edit_image`、`generate_video`、`image_to_video` 等の共通インターフェース。能力フラグ（supports_t2i, supports_video 等）。

## [ ] バックエンドレジストリ
名前で Backend を解決。利用可能/不可（API キー欠如、SD 未起動）を報告。

## [ ] 生成ジョブリクエスト型
mode (t2i/i2i/t2v/i2v)、backend、prompt、refs（@参照解決後の media ids）、パラメータ（size, seed, steps 等）。

## [ ] 生成ジョブ実行パイプライン
リクエスト受け → @解決 → Backend 呼び出し → ファイル保存 → グラフ更新 → レスポンス。エラーを構造化。

---

# フェーズ 3: Grok バックエンド

## [ ] Grok クライアント基盤
httpx 等で xAI API 呼び出し。`XAI_API_KEY` 認証。タイムアウト・エラーハンドリング。

## [ ] Grok Text-to-Image
`POST /v1/images/generations`（model: grok-imagine-image 等）。結果 URL/バイナリ取得してローカル保存。

## [ ] Grok Image-to-Image
`POST /v1/images/edits`。入力画像（path/url/base64）+ prompt。複数入力対応を検討（API 仕様に合わせる）。

## [ ] Grok Text-to-Video
xAI 動画生成 API を調査・実装。結果をローカル保存。長時間タイムアウト対応。

## [ ] Grok Image-to-Video
画像入力 + prompt で動画生成。API 仕様に合わせ実装。

## [ ] Grok パラメータ UI 向けスキーマ
aspect_ratio、n、model 名など Grok 固有パラメータの定義と API 露出。

## [ ] Grok バックエンド単体テスト / 手動確認手順
モックまたは実 API での確認メモ。キー無し時の明確なエラー。

---

# フェーズ 4: 生成 API（サーバー側）

## [ ] `POST /api/generate` エンドポイント
mode / backend / prompt / media_ids / params を受け、ジョブ実行。同期で結果ノードを返す（必要なら後で非同期化）。

## [ ] 生成進捗・長時間ジョブ対応（必要なら）
動画など時間がかかる場合: ジョブ ID + ポーリング、または SSE/WebSocket。最初は同期でも可、タイムアウトだけ十分長く。

## [ ] バックエンド一覧 API
`GET /api/backends`：利用可能バックエンドと各能力（t2i/i2i/t2v/i2v）。

## [ ] エラーレスポンス統一
API キー欠如、バックエンド不通、不正参照、生成失敗を JSON で返す。

---

# フェーズ 5: @参照

## [ ] プロンプト内 `@ImageN` / `@VideoN` パーサ
正規表現等で参照を抽出。番号と media リストの対応ルールを定義。

## [ ] 参照解決
選択中の入力リスト（またはグラフ上の候補）から media id に解決。存在しない参照はエラー。

## [ ] 複数入力の Backend への受け渡し
Grok / SD それぞれが複数画像をどう受けるかに合わせてマッピング。プロンプトから参照トークンを除去または置換するか方針決定。

## [ ] UI での入力スロット表示
Image1, Image2... として選択・並べ替え・削除。プロンプト挿入補助。

---

# フェーズ 6: Web UI（コア）

## [ ] フロントエンド基盤
単一 HTML + JS（または軽量構成）。静的配信。モダンで操作しやすいレイアウト。

## [ ] プロンプト入力 UI
テキストエリア、backend 選択、mode 選択（T2I/I2I/T2V/I2V）。mode と backend の組み合わせで無効な選択肢を隠す/無効化。

## [ ] パラメータパネル
backend/mode に応じたパラメータ（aspect ratio, steps, seed 等）。デフォルト値。

## [ ] メディアギャラリー
生成・アップロード済みメディアの一覧表示（サムネイル）。選択で入力スロットへ。

## [ ] プレビュー表示
選択中/最新生成の画像・動画を大きく表示。動画は再生コントロール。

## [ ] 生成実行ボタンとローディング
API 呼び出し、スピナー/進捗、成功時ギャラリー更新、失敗時メッセージ。

## [ ] アップロード UI
ドラッグ&ドロップ / ファイル選択。画像・動画。

## [ ] ダウンロード
各メディアにダウンロードリンク/ボタン。元ファイル名または id 付きファイル名。

---

# フェーズ 7: 生成ツリー可視化

## [ ] グラフ取得 API
`GET /api/graph`：全ノードとエッジ。

## [ ] ツリー / DAG ビュー UI
親子関係を視覚化（簡易リスト階層でも可、可能ならキャンバス/SVG）。ノードクリックでプレビュー連動。

## [ ] ノードメタデータ表示
backend、mode、prompt、seed、作成時刻など。ツリーから履歴を辿れること。

## [ ] バックエンド横断エッジの表示
例: SD 生成画像 → Grok I2V。エッジまたはノード色で backend を区別。

---

# フェーズ 8: SD WebUI バックエンド

## [ ] SD WebUI HTTP クライアント
`SD_WEBUI_URL` へ接続。ヘルスチェック（options や sd-models への GET）。未起動時は利用不可。

## [ ] モデル一覧取得
`GET /sdapi/v1/sd-models`。UI にチェックポイント一覧表示。

## [ ] モデル切替
`POST /sdapi/v1/options` で `sd_model_checkpoint` 設定。デフォルト候補: WAI-NSFW-illustrious-SDXL（インストール済みなら）。

## [ ] SD Text-to-Image
`POST /sdapi/v1/txt2img`。prompt, negative_prompt, steps, cfg_scale, width, height, sampler_name, seed 等。base64 画像を保存。

## [ ] SD Image-to-Image
`POST /sdapi/v1/img2img`。init_images + denoising_strength。入力はアプリ内メディアから。

## [ ] SD パラメータ UI 向けスキーマ
negative_prompt、steps、CFG、sampler、サイズ、seed、denoising、checkpoint を generate API / フロントに露出。

## [ ] SD 障害時の UX
接続失敗・タイムアウト・モデル無しを UI に明示。Grok は独立して動作継続。

## [ ] WAI-NSFW-illustrious-SDXL 動作確認手順
README に: WebUI `--api` 起動、モデル配置パス、推奨サイズ/sampler のメモ（ユーザー環境依存）。

## [ ] SD バックエンドとグラフ連携確認
SD 生成 → ギャラリー/ツリーに載る → 入力再利用（Grok I2V 含む）の E2E。

---

# フェーズ 9: 仕上げ・品質

## [ ] README を実装に合わせて更新
インストール、環境変数、起動、SD WebUI 前提条件、基本操作。

## [ ] CLAUDE.md を実装構造に合わせて更新
ディレクトリ構成、主要モジュール、コマンドを現状反映。

## [ ] 型チェック・フォーマット通過
`uv run black .`、`uv run ty check`（または採用したコマンド）がクリーン。

## [ ] 基本の自動テスト
パーサ（@参照）、グラフ CRUD、Backend モックでの generate パイプライン。

## [ ] 手動 E2E チェックリスト
Grok T2I/I2I/T2V/I2V、アップロード、@複数入力、ツリー、ダウンロード、SD T2I/I2I、横断再利用。

## [ ] エラー・エッジケース
空プロンプト、巨大ファイル、未対応 mode×backend、API キー無し、SD ダウン、不正 media id。

## [ ] （任意）非同期ジョブキュー
動画生成の待ち時間改善。優先度低。完了条件からは外してよい。

## [ ] （任意）LoRA / 拡張 SD パラメータ
WebUI の alwayson_scripts 等。WAI 本体動作の後で検討。
