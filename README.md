# atelier

<img src="icons/atelier.svg" width="48" height="48" alt="" align="left" />

画像・動画を **生成し、編集し、また入力に回す** ためのローカル web アプリ。

Grok（xAI Imagine）と、任意で Stable Diffusion WebUI をバックエンドに使える。生成の親子関係は **lineage** としてツリー表示・名前付き保存できる。

<br clear="all" />

## できること

- **Text → Image / Video**、**Image → Image / Video**
- 生成結果やアップロードを次の入力に再利用（複数枚可）
- **→ Image / → Video** を選ぶだけ（入力の有無で t2i / i2i 等は自動）
- バックエンド横断（例: SD で画を作り、Grok で動画化）
- lineage 単位の作業履歴（ギャラリー + ツリー、autosave）

| バックエンド | 画像 | 動画 | 備考 |
|-------------|------|------|------|
| [Grok](https://docs.x.ai/) | ○ | ○ | `XAI_API_KEY` が必要 |
| [SD WebUI](https://github.com/AUTOMATIC1111/stable-diffusion-webui) | ○ | — | 別プロセス + `--api`（任意） |

## 必要なもの

- Python **3.13+** と [uv](https://docs.astral.sh/uv/)
- Grok を使う場合: [xAI API キー](https://console.x.ai/)

## 使い方

```bash
uv sync
export XAI_API_KEY="your-key"   # Grok を使う場合
uv run atelier start
```

ブラウザで **http://127.0.0.1:8000/** を開く。

| 操作 | ヒント |
|------|--------|
| 生成 | Prompt を書いて **Generate**（`Ctrl+Enter` でも可） |
| 出力種別 | **→ Image** または **→ Video** |
| 入力追加 | 画像を D&D、またはプレビューの **Use as input** |
| 設定の復元 | **Restore setup** で当時の prompt / 入力を戻す |
| 作業の保存 | ヘッダーの lineage（10 秒ごとに自動保存） |
| 削除 | **Delete** はツリーの **葉**だけ可 |

動画生成は時間がかかることがある。UI はジョブ完了まで待つ。

### Stable Diffusion WebUI（任意）

1. WebUI を **`--api`** 付きで起動する  
2. チェックポイントを配置する（例: [WAI-NSFW-illustrious-SDXL](https://civitai.com/models/827813/wai-nsfw-illustrious-sdxl)）  
3. `export SD_WEBUI_URL=http://127.0.0.1:7860`  
4. atelier を起動し、backend で `sd_webui` を選ぶ  

SDXL / Illustrious の目安: 1024×1024、sampler `Euler a`、steps 28 前後。

## 設定

| 環境変数 | デフォルト | 意味 |
|----------|------------|------|
| `XAI_API_KEY` | （なし） | Grok API キー |
| `SD_WEBUI_URL` | `http://127.0.0.1:7860` | SD WebUI の URL |
| `ATELIER_HOST` | `0.0.0.0` | 待ち受けアドレス |
| `ATELIER_PORT` | `8000` | ポート |
| `ATELIER_DATA_DIR` | `data` | lineage・ファイルの保存先 |

```bash
uv run atelier start --host 0.0.0.0 --port 8000
uv run atelier start --reload   # 開発時
```

## 開発者向け

HTTP API・内部設計・注意点は **[CLAUDE.md](CLAUDE.md)** を参照。

```bash
uv run black .
uv run ty check
uv run pytest
```

## ライセンス

MIT — 詳細は [LICENSE](LICENSE)。
