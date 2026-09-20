#!/usr/bin/env bash
#
# set_openai_key.sh -- store OPENAI_API_KEY into .env from the clipboard,
# without the key ever being printed, echoed, logged, or otherwise
# displayed by this script (and without Claude ever reading it -- see
# CLAUDE.md at the repo root for that rule).
#
# Steps (in this order): read clipboard -> validate it looks like an
# OpenAI key (starts with "sk-") -> write it into .env -> chmod 600 .env
# -> clear the clipboard -> live connectivity test against the OpenAI API.
#
# The connectivity test is two calls: a free GET /v1/models (checks the key
# is valid) followed by a minimal POST /v1/chat/completions with max_tokens=1
# on gpt-4o-mini (checks there's actually billing/credit available). A key
# can pass the first and still fail the second with insufficient_quota if
# the account's balance is exhausted -- which is a real account state, not a
# code bug, and /v1/models alone can't detect it. The second call is a real,
# tiny (well under a cent) billable request, not a free one.
#
# Output is a single success/failure line. Never the key itself.
#
# Usage:
#   1. Copy your OpenAI API key to the clipboard (and nowhere else, e.g.
#      never paste it into a chat).
#   2. ./scripts/set_openai_key.sh

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

ENV_FILE=".env"
TMP_ENV=""
CURL_CFG=""
QUOTA_BODY=""

cleanup() {
  [ -n "$TMP_ENV" ] && rm -f "$TMP_ENV" 2>/dev/null
  [ -n "$CURL_CFG" ] && rm -f "$CURL_CFG" 2>/dev/null
  [ -n "$QUOTA_BODY" ] && rm -f "$QUOTA_BODY" 2>/dev/null
  return 0
}
trap cleanup EXIT

clipboard_read() {
  if command -v pbpaste >/dev/null 2>&1; then
    pbpaste
  elif command -v wl-paste >/dev/null 2>&1; then
    wl-paste
  elif command -v xclip >/dev/null 2>&1; then
    xclip -selection clipboard -o
  elif command -v xsel >/dev/null 2>&1; then
    xsel --clipboard --output
  else
    return 1
  fi
}

clipboard_clear() {
  if command -v pbcopy >/dev/null 2>&1; then
    printf '' | pbcopy
  elif command -v wl-copy >/dev/null 2>&1; then
    printf '' | wl-copy
  elif command -v xclip >/dev/null 2>&1; then
    printf '' | xclip -selection clipboard
  elif command -v xsel >/dev/null 2>&1; then
    printf '' | xsel --clipboard --input
  fi
}

fail() {
  clipboard_clear 2>/dev/null || true
  echo "[ai-butler] 失敗: $1"
  exit 1
}

# 1. clipboard取得
KEY="$(clipboard_read)" || fail "クリップボードを取得できませんでした(pbpaste/wl-paste/xclip/xselが見つかりません)"
KEY="$(printf '%s' "$KEY" | tr -d '\n\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
[ -n "$KEY" ] || fail "クリップボードが空でした"

# 2. sk-で始まる形式か検証
case "$KEY" in
  sk-*) : ;;
  *) fail "クリップボードの内容が sk- で始まる形式ではありません" ;;
esac
[ "${#KEY}" -ge 20 ] || fail "クリップボードの内容が短すぎます(APIキーとして不自然です)"

# 3. .env へ保存(他の設定行は保持し、OPENAI_API_KEY行だけ置き換える)
TMP_ENV="$(mktemp)"
if [ -f "$ENV_FILE" ]; then
  grep -v '^OPENAI_API_KEY=' "$ENV_FILE" > "$TMP_ENV" || true
fi
printf 'OPENAI_API_KEY=%s\n' "$KEY" >> "$TMP_ENV"
mv "$TMP_ENV" "$ENV_FILE"
TMP_ENV=""

# 4. パーミッションを制限
chmod 600 "$ENV_FILE"

# 5. クリップボード消去
clipboard_clear

# 6. OpenAI APIへの接続テスト(2段階)
#    ps/プロセス一覧にキーが載らないよう、コマンドライン引数ではなく
#    一時curl設定ファイル(600権限、使用後に削除)経由でヘッダーを渡す。
CURL_CFG="$(mktemp)"
chmod 600 "$CURL_CFG"
printf 'header = "Authorization: Bearer %s"\n' "$KEY" > "$CURL_CFG"

# 6a. 認証チェック(無料。GET /v1/models はクレジット残高が無くても200を返す)
HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 -K "$CURL_CFG" https://api.openai.com/v1/models 2>/dev/null || echo "000")"

case "$HTTP_CODE" in
  200) : ;;
  401|403)
    unset KEY
    echo "[ai-butler] 失敗: 認証エラー(キーが無効か、権限が無い可能性があります)"
    exit 1
    ;;
  000)
    unset KEY
    echo "[ai-butler] 失敗: ネットワークエラー(OpenAI APIに到達できませんでした)"
    exit 1
    ;;
  *)
    unset KEY
    echo "[ai-butler] 失敗: 予期しない応答でした(models, HTTPステータス ${HTTP_CODE})"
    exit 1
    ;;
esac

# 6b. 残高チェック(認証は通ったが、クレジット残高が無いと実際のRealtime API
#     セッションは insufficient_quota で弾かれる。それをここで検出するため、
#     ごく小さい実際の課金リクエスト(gpt-4o-mini, max_tokens=1)を1回叩く。
#     コストはごくわずかだが、無料ではない点に注意。)
printf 'header = "Content-Type: application/json"\n' >> "$CURL_CFG"
unset KEY

QUOTA_BODY="$(mktemp)"
HTTP_CODE2="$(curl -s -o "$QUOTA_BODY" -w '%{http_code}' --max-time 20 -K "$CURL_CFG" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}],"max_tokens":1}' \
  https://api.openai.com/v1/chat/completions 2>/dev/null || echo "000")"

case "$HTTP_CODE2" in
  200)
    echo "[ai-butler] 成功: .envに保存し、OpenAI APIへの接続とクレジット残高を確認しました"
    ;;
  429)
    if grep -q "insufficient_quota" "$QUOTA_BODY" 2>/dev/null; then
      echo "[ai-butler] 失敗: OpenAIアカウントのクレジット残高が不足しています(認証は成功。platform.openai.comで支払い設定・チャージが必要です)"
    else
      echo "[ai-butler] 失敗: レート制限に達しました(429)。少し待って再実行してください"
    fi
    exit 1
    ;;
  401|403)
    echo "[ai-butler] 失敗: 認証エラー(chat/completionsで権限が無い可能性があります)"
    exit 1
    ;;
  000)
    echo "[ai-butler] 失敗: ネットワークエラー(OpenAI APIに到達できませんでした)"
    exit 1
    ;;
  *)
    echo "[ai-butler] 失敗: 予期しない応答でした(chat/completions, HTTPステータス ${HTTP_CODE2})"
    exit 1
    ;;
esac
