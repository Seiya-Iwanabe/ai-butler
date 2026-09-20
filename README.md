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
- デスクトップに常駐する半透明のオーブ型ウィジェットが、待機中は静かに呼吸するように明滅し、
  せいちゃんの声を聞いている間はマイク入力のスペクトラムで、デヴィが話している間は
  デヴィ自身の声のスペクトラムでリアルタイムに波打つ(詳細は下記「デスクトップビジュアライザー」)。

## 動作環境について(重要・正直に書きます)

このリポジトリは開発用のサンドボックス(マイク/スピーカーの無い Linux コンテナ)で書きました。
そのため以下を区別して書いています。

- **実際に動かして確認したこと**: 各モジュールのロジック(下記「テスト」参照)、
  OpenAI Realtime API のイベント/フィールド形式(`openai-python` の生成済み型定義を直接読んで
  裏取り — 詳細は `docs/DESIGN.md`)、`claude --help` によるCLIフラグの実在確認。ビジュアライザーの
  Canvas描画ロジックはヘッドレスブラウザで実際にレンダリングしてスクリーンショットで確認し、
  音声レベル/スペクトラム計算はサイン波を使った自動テストで検証済み。ウィンドウ生成に失敗した
  場合(pywebview未導入・GUIバックエンド無し)にデヴィ本体の音声機能が巻き込まれず正常動作を
  続けることも実際にエラーを起こして確認済み。ホットキー処理は、実際にmacOS実機で
  ビジュアライザーと同時に使うと `pynput` がTSM(Text Services Manager)アサーションで
  クラッシュすることが利用者の実機検証で判明したため、`pynput` をやめて独自のQuartz実装に
  置き換えた(根拠は `docs/DESIGN.md` 参照)。パース処理(キー文字列 → キーコード)は
  自動テストで検証済み。
- **実行環境の制約で確認できていないこと**: 実際のマイク/スピーカーでの音声往復、実際の
  OpenAI APIキーでのWebSocket接続、macOS実機での Option+Space の実際の反応(独自Quartz実装は
  根本原因の調査に基づいて設計したが、この環境にはmacOSが無いため動作そのものは実機依存)、
  そしてビジュアライザーウィジェットの**実際の見た目・常に最前面・透明背景としての動作**
  (macOSが無いため未検証)。`ai_butler/hotkey.py`はmacOS専用の`Quartz`モジュールに依存するため、
  Linux環境ではimportすら確認できない(構文チェックのみ)。

導入したらまず「setup-tokenで認証 → `python -m ai_butler` → 短く話しかけてみる」で
一通り確認することを強くおすすめします。

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`OPENAI_API_KEY` は **チャットに貼らず**、`.env` を手編集もせず、`scripts/set_openai_key.sh` を
使って設定してください。クリップボード経由で読み取り、`.env` に保存し、パーミッションを
`600` に制限し、クリップボードを消去したうえでOpenAI APIへの接続テストまで行います
(キーの中身はスクリプトの出力にも一切出しません)。

接続テストは2段階です。まず無料の `GET /v1/models` で認証を確認し、続けて
`gpt-4o-mini` に `max_tokens=1` で実際に1リクエスト投げてクレジット残高も確認します
(認証だけ通って残高ゼロ、というケースを事前に検出するため)。後者はごく小さいですが
**実際に課金されるリクエスト**です。

```bash
# 1. OpenAI APIキーをクリップボードにコピー
# 2. 実行:
./scripts/set_openai_key.sh
```

macOSの場合、PortAudio(sounddeviceの依存)は Homebrew で入ります。

```bash
brew install portaudio
```

Claude Code CLI がインストール済みで `claude` コマンドが PATH に通っていることを確認してください
(`claude --version`)。

### macOS: 権限まわり

- **マイク**: 初回起動時にOSのマイクアクセス許可ダイアログが出ます。許可してください。
- **グローバルホットキー**: Quartzのイベントタップ(`CGEventTapCreate`)でOSレベルのキー監視を
  するため、ターミナル(または作ったアプリ)に **システム設定 → プライバシーとセキュリティ →
  アクセシビリティ** の許可が必要です。許可しないと Option+Space が反応しません
  (許可が無いとタップの作成自体に失敗し、ログに警告が出てホットキー無しで動作を続けます)。

## 実行

```bash
python -m ai_butler
```

起動すると「デヴィが起動したよ」とログに出ます。Option+Spaceで聞き取りをONにしてから話しかけてください。
Ctrl+Cで終了します。

## デスクトップビジュアライザー

`python -m ai_butler` を起動すると、既定でデスクトップの隅(既定は右下)に半透明のオーブ型
ウィジェットが常に最前面で表示されます。

- 待機中: ゆっくり呼吸するように明滅
- せいちゃんの声を聞いている間: マイク入力のスペクトラム(周波数帯ごとの強さ)に合わせてリング状に波打つ
- デヴィが話している間: デヴィ自身の音声出力のスペクトラムに合わせて波打つ

これは pywebview を使い、Canvas(`ai_butler/visualizer/orb.html`)で描いた見た目を透明・
フレームレスなウィンドウに表示する形で実装しています。マイクを二重に掴むことはしておらず、
ai_butler が既に扱っているマイク入力・音声出力のPCMデータをそのまま使ってスペクトラムを
計算しています。

**フォールバック設計**: `pywebview` が無い/GUIバックエンド(macOSなら通常問題ありませんが、
Linuxなら GTK か Qt が必要)が無い等でウィジェットの起動に失敗しても、ログに警告を出した上で
デヴィ本体(音声のやり取り)はそのまま動き続けます。ウィジェットを完全に切りたい場合は
`.env` で `AI_BUTLER_VISUALIZER=0` にしてください。

ウィジェットを閉じるとデヴィ全体も終了します(バックグラウンドの音声ループとウィンドウの
生死を連動させているため)。逆にCtrl+Cで終了した場合もウィジェットが閉じます。ただし
Ctrl+CはpywebviewのネイティブGUIループをブロックしている間はすぐには効かないことがあります
(ウィジェットを閉じるか、バックグラウンド実行中なら `claude stop <session-id>` を使ってください)。

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
| `AI_BUTLER_VISUALIZER` | `1` | デスクトップビジュアライザーの有効/無効 |
| `AI_BUTLER_VISUALIZER_CORNER` | `bottom-right` | ウィジェットを表示する画面の隅 |

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
- `tests/test_level_meter.py`: 音声レベル/スペクトラム計算(サイン波を生成し、狙った周波数帯に
  正しくピークが出るか等を検証)

`ai_butler/audio_io.py`(マイク/スピーカー入出力そのもの)と `ai_butler/hotkey.py`(実際の
キー入力検知)、`ai_butler/visualizer/window.py`(実際のウィンドウ表示)は実ハードウェア/GUI依存
のため自動テストの対象外です。手元での動作確認をお願いします。

## アーキテクチャと根拠

`docs/DESIGN.md` に、なぜこの設計にしたか・OpenAI Realtime APIの各イベント名やフィールド形式を
何を根拠に確定させたか(公式ドキュメントサイトがサンドボックスからアクセスできなかったため、
`openai/openai-python` の生成済み型定義を直接読んで裏取りしました)をまとめています。
