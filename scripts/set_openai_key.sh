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

cleanup() {
  [ -n "$TMP_ENV" ] && rm -f "$TMP_ENV" 2>/dev/null
  [ -n "$CURL_CFG" ] && rm -f "$CURL_CFG" 2>/dev/null
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

# 6. OpenAI APIへの接続テスト
#    ps/プロセス一覧にキーが載らないよう、コマンドライン引数ではなく
#    一時curl設定ファイル(600権限、使用後に削除)経由でヘッダーを渡す。
CURL_CFG="$(mktemp)"
chmod 600 "$CURL_CFG"
printf 'header = "Authorization: Bearer %s"\n' "$KEY" > "$CURL_CFG"
unset KEY

HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 -K "$CURL_CFG" https://api.openai.com/v1/models 2>/dev/null || echo "000")"

case "$HTTP_CODE" in
  200)
    echo "[ai-butler] 成功: .envに保存し、OpenAI APIへの接続を確認しました"
    ;;
  401|403)
    echo "[ai-butler] 失敗: 認証エラー(キーが無効か、権限が無い可能性があります)"
    exit 1
    ;;
  000)
    echo "[ai-butler] 失敗: ネットワークエラー(OpenAI APIに到達できませんでした)"
    exit 1
    ;;
  *)
    echo "[ai-butler] 失敗: 予期しない応答でした(HTTPステータス ${HTTP_CODE})"
    exit 1
    ;;
esac
