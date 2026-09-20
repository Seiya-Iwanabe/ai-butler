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
- `ai_butler/hotkey.py`: `pynput.keyboard.GlobalHotKeys` でOSレベルのキー入力を監視し、
  別スレッドから `loop.call_soon_threadsafe` でasyncio側に伝える。
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
