# ai-butler

ai音声モデルを活用した自分専用の執事「デヴィ」。

OpenAI Realtime API (`gpt-realtime-2.1`) でせいちゃんの声を聞き取って声で返事をし、
開発タスクは全部せいちゃんのマシンで動いている **Claude Code CLI** にそのまま丸ごと渡す、
常駐の音声アシスタントです。

## 何をするツールか

- マイクの声を OpenAI Realtime API (`gpt-realtime-2.1`) にストリーミングし、返事も音声で受け取ってスピーカーから再生する。
- 開発/コーディング系のタスクだと判断したら、自分ではコードを書かず `claude -p "<タスク>"` を
  サブプロセスとして呼び出し、結果が返ってきたら要約して話す。
- デヴィが喋っている間と喋り終わった直後は、スピーカーの音をマイクが拾って誤反応しないように
  マイク入力を止める。
- **Option + Space** でマイクのON/OFF(聞き取りの有効/無効)をトグルする。

## 動作環境について(重要・正直に書きます)

このリポジトリは開発用のサンドボックス(マイク/スピーカーの無い Linux コンテナ)で書きました。
そのため以下を区別して書いています。

- **実際に動かして確認したこと**: 各モジュールのロジック(下記「テスト」参照)、全モジュールの
  import(グローバルホットキー含む。Linuxでは仮想ディスプレイ Xvfb を立てて確認)、
  OpenAI Realtime API のイベント/フィールド形式(`openai-python` の生成済み型定義を直接読んで
  裏取り — 詳細は `docs/DESIGN.md`)、`claude --help` によるCLIフラグの実在確認。
- **実行環境の制約で確認できていないこと**: 実際のマイク/スピーカーでの音声往復、実際の
  OpenAI APIキーでのWebSocket接続、macOS実機での Option+Space の動作(pynputはmacOSでは
  Xlibではなく Quartz バックエンドを使うため動くはずですが、実機未検証です)。

導入したらまず「setup-tokenで認証 → `python -m ai_butler` → 短く話しかけてみる」で
一通り確認することを強くおすすめします。

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env を開いて OPENAI_API_KEY を設定
```

macOSの場合、PortAudio(sounddeviceの依存)は Homebrew で入ります。

```bash
brew install portaudio
```

Claude Code CLI がインストール済みで `claude` コマンドが PATH に通っていることを確認してください
(`claude --version`)。

### macOS: 権限まわり

- **マイク**: 初回起動時にOSのマイクアクセス許可ダイアログが出ます。許可してください。
- **グローバルホットキー**: `pynput` でOSレベルのキー監視をするため、ターミナル(または作った
  アプリ)に **システム設定 → プライバシーとセキュリティ → アクセシビリティ** の許可が必要です。
  許可しないと Option+Space が反応しません。

## 実行

```bash
python -m ai_butler
```

起動すると「デヴィが起動したよ」とログに出ます。Option+Spaceで聞き取りをONにしてから話しかけてください。
Ctrl+Cで終了します。

## Claude Codeへの権限委譲について(要理解のうえ設定)

音声でタスクを投げてから結果が返るまでは対話なしの `claude -p` (非対話/ヘッドレス実行)です。
TTYが無いため、通常の許可プロンプトには誰も答えられません。

- `CLAUDE_CODE_PERMISSION_MODE` を**未設定のまま**にすると、承認が必要な操作は基本的に
  拒否されます(安全寄りだが、任せられる作業が限られる)。
- 何でも任せたい場合は `.env` で `CLAUDE_CODE_PERMISSION_MODE=bypassPermissions` などを
  明示的に設定してください。これは全ての権限チェックを飛ばすので、信頼できる環境・
  リポジトリでのみ使うことをおすすめします(`claude --help` 自体が
  「Recommended only for sandboxes with no internet access」と警告しています)。

## 設定項目

`.env.example` を参照してください。主なもの:

| 変数 | デフォルト | 説明 |
|---|---|---|
| `OPENAI_API_KEY` | (必須) | Realtime API を使えるAPIキー |
| `OPENAI_REALTIME_MODEL` | `gpt-realtime-2.1` | Realtimeモデル |
| `AI_BUTLER_VOICE` | `shimmer` | 声質。`alloy/ash/ballad/coral/echo/sage/shimmer/verse/marin/cedar` から選択。各声の「キャラクター」はOpenAIの公式説明が見つからなかったため、実際に聞いて好みで選んでください |
| `AI_BUTLER_HOTKEY` | `<alt>+<space>` | 聞き取りON/OFFのホットキー(Option=`<alt>`) |
| `AI_BUTLER_MIC_COOLDOWN_MS` | `600` | デヴィが喋り終えてからマイクを再開するまでの待ち時間 |
| `CLAUDE_CODE_COMMAND` | `claude` | Claude Code CLIのコマンド/パス |
| `CLAUDE_CODE_PERMISSION_MODE` | (未設定) | 上記「権限委譲について」参照 |
| `CLAUDE_CODE_TIMEOUT_SEC` | `1800` | 1タスクのタイムアウト秒数 |

## テスト

ネットワークや実マイク/スピーカーが要らない範囲は自動テストで検証しています。

```bash
pip install -r requirements-dev.txt
pytest -q
```

- `tests/test_realtime_protocol.py`: Realtime APIに送るJSONイベントの形が仕様通りか
- `tests/test_mic_gate.py`: 発話中/発話直後のミュート、クールダウンの再オープン挙動
- `tests/test_claude_bridge.py`: `claude` CLI呼び出しの組み立てと、成功/失敗/タイムアウトの挙動
  (スタブスクリプトで実プロセスを起動して検証)
- `tests/test_config.py`: 環境変数の読み込みとバリデーション

`ai_butler/audio_io.py`(マイク/スピーカー入出力そのもの)と `ai_butler/hotkey.py`(実際の
キー入力検知)は実ハードウェア依存のため自動テストの対象外です。手元での動作確認をお願いします。

## アーキテクチャと根拠

`docs/DESIGN.md` に、なぜこの設計にしたか・OpenAI Realtime APIの各イベント名やフィールド形式を
何を根拠に確定させたか(公式ドキュメントサイトがサンドボックスからアクセスできなかったため、
`openai/openai-python` の生成済み型定義を直接読んで裏取りしました)をまとめています。
