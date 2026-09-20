# 設計メモと根拠

## 全体構成

```
マイク --(PCM16 24kHz)--> RealtimeSession --WebSocket--> OpenAI Realtime API (gpt-realtime-2.1)
                                  ^                                  |
                                  | function_call_output/response.create
                                  |                                  v
                          claude_bridge.run_claude_code    response.output_audio.delta
                          (`claude -p "<task>"` subprocess)         |
                                                                     v
                                                             SpeakerPlayer --> スピーカー
```

- `ai_butler/realtime_protocol.py`: Realtime APIに送るJSONイベントを組み立てる純粋関数群。
  ネットワークI/Oなし、ユニットテストのみで検証可能。
- `ai_butler/realtime_client.py`: WebSocket接続とイベントディスパッチ。音声デルタをスピーカーへ、
  `run_claude_code` の function call を検知したら非同期タスクとして `claude_bridge` へ委譲。
- `ai_butler/claude_bridge.py`: `claude -p "<task>" --output-format text` をサブプロセスとして
  起動し、標準出力をそのままツール結果としてRealtime APIに返す。
- `ai_butler/mic_gate.py`: 「ホットキーで聞き取りON/OFF」と「デヴィの発話中+クールダウン中は
  ミュート」という2つの独立したスイッチを持つ状態機械。両方が「開いて」いる時だけマイクの
  フレームを実際にAPIへ送る(`ai_butler/audio_io.py` のコールバックが毎フレーム
  `should_capture()` を見る)。
- `ai_butler/hotkey.py`: Quartzの `CGEventTapCreate` を直接使った自前実装でOSレベルのキー入力を
  監視し、別スレッドから `loop.call_soon_threadsafe` でasyncio側に伝える。当初は
  `pynput.keyboard.GlobalHotKeys` を使っていたが、ビジュアライザー追加後に実機で
  クラッシュが判明し置き換えた — 詳細は本ファイル末尾「グローバルホットキーの実装を
  pynputから置き換えた理由」を参照。
- `ai_butler/persona.py`: デヴィのキャラクター設定(system instructions)。「開発タスクは
  自分でやらず必ず `run_claude_code` を呼ぶ」「呼ぶ時は先に所要時間の目安を一言言う」という
  行動契約をここで明文化している。時間の見積もりを別途コード側で計算していないのは、
  Realtime APIの1レスポンスに「音声メッセージ + function call」の両方を含められる
  (後述の根拠参照)ため、モデル自身に喋らせる方がシンプルで確実だと判断したため。

## なぜマイクミュートを「デヴィの発話中+短いクールダウン」にしたか

スピーカーで再生した音声がそのままマイクに回り込むと、Realtime APIのサーバー側VAD
(`turn_detection`)がそれを新しい発話だと誤検知し、自分の声に反応してループする恐れがある。
そのため:

1. `response.output_audio.delta` の最初の1件を受け取った瞬間にゲートを閉じる
   (`MicGate.on_playback_started`)。
2. `response.output_audio.done` を受け取ったら即座に開けるのではなく、
   `AI_BUTLER_MIC_COOLDOWN_MS`(デフォルト600ms)だけ待ってから開ける
   (`MicGate.on_playback_finished` → `asyncio` の `call_later`)。スピーカーの物理的な
   残響やOS側バッファのラグを考慮した余裕。

`tests/test_mic_gate.py` でこの状態遷移(発話開始で閉じる、終了後もクールダウン中は閉じたまま、
クールダウン経過後に開く、クールダウン中に次の発話が始まったら再スケジュールされる)を検証済み。

## OpenAI Realtime API の仕様確認について(根拠)

作業したサンドボックス環境では `developers.openai.com` / `platform.openai.com` への
`WebFetch` がネットワークプロキシでブロックされており(`EGRESS_BLOCKED`)、公式ドキュメントを
直接読むことができなかった。そこで、Web検索の要約で得た情報(下記)を、
**OpenAIが公開している公式Python SDK `openai/openai-python` のリポジトリを実際にクローンし、
OpenAPI仕様から自動生成された型定義ファイル(`src/openai/types/realtime/*.py`)を直接読む**
ことで裏取りした。生成コードなので、サーバー側の実際のJSONスキーマと一致していると考えてよい。

確認した主な事実と、その裏取り元:

| 事実 | 裏取り方法 |
|---|---|
| モデルID文字列は `"gpt-realtime-2.1"` (2026年7月にリリース) | Web検索(OpenAI公式発表・DevCommunityの告知)+ `realtime_session_create_request_param.py` の `model` フィールドのLiteral型に実在を確認 |
| WebSocket接続先は `wss://api.openai.com/v1/realtime?model=<model>`、認証は `Authorization: Bearer <API key>` ヘッダー | `openai-python` の `src/openai/resources/realtime/realtime.py` の `_connect_ws`/`_prepare_url` 実装を直接読んで確認 |
| `session.update` の `session` は `{"type": "realtime", "audio": {"input": {...}, "output": {...}}, "instructions": ..., "tools": [...]}` という入れ子構造(2025年8月のGA版で、旧beta版の `voice`/`modalities` トップレベル形式から変更された) | `realtime_session_create_request_param.py`, `realtime_audio_config_*_param.py` を直接読んで確認 |
| 音声フォーマットは `{"type": "audio/pcm", "rate": 24000}`(PCM16, 24kHz, モノラル)のみ `rate` 指定可 | `realtime_audio_formats_param.py` |
| turn_detectionは `server_vad` と `semantic_vad` の2種類 | `realtime_audio_input_turn_detection_param.py` |
| voiceの選択肢は `alloy, ash, ballad, coral, echo, sage, shimmer, verse, marin, cedar` | `realtime_audio_config_output_param.py` |
| function toolは `{"type": "function", "name", "description", "parameters"}` という**フラットな**構造(Chat Completions/Responses APIの `{"type":"function","function":{...}}` という入れ子形式とは異なる) | `realtime_function_tool_param.py` |
| function callの結果を返すには `conversation.item.create` で `{"type": "function_call_output", "call_id", "output"}` を送り、続けて `response.create` を送る必要がある(自動では次のレスポンスは生成されない) | `realtime_conversation_item_function_call_output_param.py` の docstring、および `response_create_event_param.py` の docstring(「A Response will include at least one Item, and may have two, in which case the second will be a function call」との記述から、1つのレスポンスに音声メッセージとfunction callの両方が載り得ることも確認) |
| 音声デルタ/完了・レスポンス完了・function引数確定・発話検知の各サーバーイベント名は `response.output_audio.delta` / `response.output_audio.done` / `response.done` / `response.function_call_arguments.done` / `input_audio_buffer.speech_started` / `input_audio_buffer.speech_stopped`(いずれも各イベントクラスの `type: Literal[...]` フィールドで確認。GA版で `response.audio.delta` から `response.output_audio.delta` へ名称変更されている点に注意) | `response_audio_delta_event.py`, `response_audio_done_event.py`, `response_done_event.py`, `response_function_call_arguments_done_event.py`, `input_audio_buffer_speech_started_event.py`, `input_audio_buffer_speech_stopped_event.py` |
| `websockets` ライブラリ(v17系)の `connect()` は `additional_headers` キーワード引数を取る(旧 `extra_headers` ではない) | インストール済み `websockets==17.1` の `inspect.signature` で実機確認 |

`openai/openai-python` のクローンは確認作業のためだけに一時的に行い、参照後に削除した(このリポジトリには含まれていない)。

## Claude Code CLI呼び出しについて(根拠)

このセッション自体がClaude Codeとして動作している環境で `claude --help` を実行し、以下を実機確認した:

- `-p, --print`: 非対話モードで実行し結果を表示して終了
- `--output-format <text|json|stream-json>`: 出力形式(デフォルト `text`)
- `--permission-mode <acceptEdits|auto|bypassPermissions|manual|dontAsk|plan>`
- `--allow-dangerously-skip-permissions`: 「インターネットに繋がっていないサンドボックス以外では
  非推奨」と明記されている

これらを踏まえ、`claude_bridge.py` はデフォルトで `--permission-mode` を指定しない
(＝承認が必要な操作は拒否される安全寄りの挙動)構成とし、フル自動で任せたい場合は
利用者が明示的に `.env` で設定する形にした。

## 既知の限界・未検証事項

- 実際のマイク/スピーカーでの音声往復、実APIキーでのWebSocket通信は、この開発環境に
  ハードウェアもAPIキーも無いため未検証。
- `ai_butler/hotkey.py` はLinux上で仮想ディスプレイ(Xvfb)を使えばimportできることまでは確認したが、
  実際のキー押下検知はmacOS実機でのみ確認できる。
- Claude Codeへのタスク実行中(数分〜数十分かかりうる)にユーザーが話しかけると、
  `semantic_vad` の `create_response: true` によって並行で別レスポンスが生成される設計にしている
  (待ち時間中の雑談を受け付けられるメリットがある)。ただしこの並行レスポンスと、
  Claude Codeの結果が返ってきたタイミングでの `response.create` が衝突し、
  Realtime API側が「既に進行中のレスポンスがある」とエラーを返す可能性は理論上ある
  (Realtime APIは同時に1つしかデフォルト会話に書き込めない制約があるため)。頻度は
  低いと見込むが、実運用で頻発するようであれば、ツール結果の `response.create` を
  「進行中のレスポンスが無いことを確認してから送る」ようにキューイングする改修が必要。

## デスクトップビジュアライザー(`ai_butler/visualizer/`)

### 構成

- `level_meter.py`: PCM16バイト列からRMS/周波数帯スペクトラムを計算する純粋関数群。I/O無し、
  numpyのFFTのみ使用。サイン波を自作してユニットテストで検証(`tests/test_level_meter.py`)。
- `controller.py`: 音声コールバックのスレッド(PortAudioのコールバックスレッド、asyncioの
  イベントループ)から呼ばれる `report_mic_level`/`report_output_level` はロックを取って数値を
  保存するだけの軽量処理とし、実際にGUI(`window.evaluate_js`)を呼ぶのは専用のポンプスレッドが
  ~30fpsで行う。これはGUI/IPC呼び出しの遅延がリアルタイム音声パスに影響しないようにするため。
- `window.py`: pywebviewで透明・フレームレス・最前面のウィンドウを作り、`orb.html`をロードする。
- `orb.html`: 素のCanvas 2D。pywebview固有のAPIには依存せず、`window.setVisualizerState()`/
  `window.setVisualizerSpectrum()` というグローバル関数をPython側が `evaluate_js` 越しに呼ぶだけ
  なので、単体でも(ヘッドレスブラウザでも)描画確認できる。

### なぜPyObjC直描画ではなくpywebview+HTMLにしたか

macOS実機が無い開発環境で、実際に「動くところを見て確認する」ことを優先した。pywebview+Canvasなら
Playwrightのヘッドレスブラウザで実際にレンダリングしてスクリーンショットを撮って確認できるが、
PyObJC(Quartz)で直接描画するコードは、この環境では構文チェックしかできない。

### 実際に見つかった・直したバグ(この開発環境での動作確認で発見)

このサンドボックスにはmacOSが無いため「本番相当の確認」はできないが、Linux+Xvfb+pywebview
(GTK/QTバックエンドは未インストール)の組み合わせで実際にコードを動かし、以下の実バグを発見・修正した:

1. `background_color="#00000000"`(8桁・アルファ付き)を渡していたが、pywebviewは
   `#RRGGBB`(6桁)のみを受け付け、`ValueError`で即座に落ちる仕様だった。透明化は別の
   `transparent=True` 引数が担当しており、`background_color`はロード直後に一瞬映る
   プレースホルダー色でしかない。`#000000`に修正。
2. `webview.start()` が(GTK/QTどちらのGUIバックエンドも無い環境で)`WebViewException` を
   送出するケースが、`app.py`の`main()`で捕捉されておらず、デヴィの音声ループごと
   プロセスがクラッシュしていた。`run_blocking()`周りを try/except で囲み、失敗時は
   バックグラウンドの非同期パイプラインをそのままヘッドレス動作として待ち受ける形に修正。
3. 上記2のフォールバック時、`_run_pipeline`のfinallyが呼ぶ`visualizer.close_window_if_open()`
   →`window.destroy()`が、一度も`webview.start()`が成功していないウィンドウに対しては
   **無限にハングする**ことが分かった(GUIループが無いため`destroy`要求を処理する相手がいない)。
   `VisualizerWindow`に`_started`フラグを持たせ、`run()`が実際に開始できた場合のみ
   `close()`が`destroy()`を呼ぶように修正。
4. `spectrum_bands()`の各周波数帯の集計に`.mean()`を使っていたところ、このFFT分解能
   (24000Hz/N個のサンプル)では1帯域が100ビン超に及ぶことがあり、純音のように1〜2ビンに
   エネルギーが集中する信号だと平均を取ることでほぼゼロまで薄まってしまうバグがあった
   (ユニットテストで「3kHzの純音を入れても対応する帯域がほとんど反応しない」形で発覚)。
   `.max()`(帯域内で最も強い成分を採用)に変更。バーグラフ型スペクトラムビジュアライザーの
   一般的な実装とも一致する。

### 未検証のまま残っている部分

- macOS実機での実際の見た目・常に最前面・透明ウィンドウとしての挙動そのもの。
- ウィジェットを実際に閉じた時に`on_closed`が発火し、デヴィ本体が正しく終了するか
  (Linux+GUIバックエンド無しの環境では`webview.start()`自体が即座に失敗するため、
  「ウィンドウが実際に開いて、後から閉じられる」という正常系そのものが検証できていない)。
- `window.evaluate_js`/`window.destroy()`がpywebviewのドキュメント通り本当にどのスレッドから
  呼んでも安全か。

## グローバルホットキーの実装を pynput から置き換えた理由

デスクトップビジュアライザー追加後、利用者の実機(macOS)で `python -m ai_butler` を起動すると
TSM(Text Services Manager)のアサーションでクラッシュする不具合が報告された。原因を推測ではなく
`pynput` 自体のソースコード(このリポジトリの venv にインストールされていたもの)を読んで特定した:

1. `pynput/keyboard/_darwin.py` の `Listener._run()` は、リスナーを開始するたびに必ず
   `with keycode_context() as context:` を実行する。
2. `pynput/_util/darwin.py` の `keycode_context()` は `TISCopyCurrentKeyboardInputSource()` など
   Carbonの Text Services Manager (TSM) の関数を呼び出す。これはキーコードを実際の文字列
   (現在のキーボードレイアウトに応じた文字)に変換するために必要な処理。
3. `Listener._run()` は **pynputが内部で新しく作るリスナー専用スレッド**の中で実行される
   (`Listener`は`threading.Thread`のサブクラス)。つまり `.start()` をどのスレッドから呼んでも、
   TSM呼び出し自体は常にpynputの内部スレッド(メインスレッドではない)で発生する。
4. Appleの TSM は「メインスレッドからしか呼んではいけない」という制約を持つ。この制約は、
   プロセス内に実際に動いている Cocoa アプリ(`NSApplication`)が存在する場合に厳格に
   アサーションとして効いてくる。ai_butlerにビジュアライザー(pywebview)を追加したことで、
   プロセスのメインスレッドに本物の `NSApplication` イベントループが立つようになり、
   このアサーションが顕在化してクラッシュした、と考えられる(ビジュアライザー追加前は
   `NSApplication` が存在しないヘッドレスなCLIプロセスだったため、同じpynputの実装でも
   問題が表面化していなかった可能性が高い)。

この根本原因はスレッドの呼び出し順序を工夫しても解決しない(TSM呼び出し自体がpynputの内部
スレッドに固定されているため)。そのため、pynputの高水準API(`GlobalHotKeys`/`Listener`)を
やめ、TSMを一切使わない自前実装に置き換えた:

- `ai_butler/hotkey_combo.py`: ホットキー文字列(例: `<alt>+<space>`)を「修飾キーのビットマスク」
  と「キーコード」に変換する純粋関数。Quartz依存なし、どの環境でもユニットテスト可能
  (`tests/test_hotkey_combo.py`)。
- `ai_butler/hotkey.py`: `Quartz.CGEventTapCreate` を直接使い、押されたキーの**物理的な
  仮想キーコード**(`kVK_Space` = 49 など、キーボードレイアウトに依存しない macOS の
  定数)と修飾キーのフラグビットだけを見て判定する。文字への変換が一切不要なため、TSMを
  呼び出すコード自体が存在しない。

この置き換えにより、ビジュアライザーと同時に使ってもTSMアサーションが起きる経路自体が
無くなったはずだが、**このサンドボックスにはmacOSも `pyobjc-framework-Quartz` をビルドできる
環境も無いため、修正後の動作そのものは実機で確認できていない**(`pyobjc-framework-Quartz`は
`sw_vers`などmacOS専用ツールに依存しビルドすら失敗する)。`hotkey_combo.py`のパースロジックは
自動テストで検証済みだが、`hotkey.py`自体は構文チェックのみで、importすら確認できていない
(以前の`pynput`版は仮想ディスプレイXvfbを使えばLinuxでも一応importできたが、Quartzは
純粋にmacOS専用でLinux上でビルドする方法が無いため、この点はむしろ以前より検証範囲が狭い)。
