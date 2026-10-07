#!/usr/bin/env bash
# 把卡片樣板填好值，發到 Teams。
#
# 用法：bash scripts/teams.sh <樣板.json> '<變數 JSON>'
#   樣板裡的 {{name}} 會換成變數 JSON 裡的 name；沒有 url 時拿掉「前往購票」按鈕。
#
# 環境變數：TEAMS_WEBHOOK_URL（Teams Workflows 建立的 webhook 網址）
set -euo pipefail

template="$1"
variables="${2:-{\}}"

card=$(jq --argjson vars "$variables" '
  walk(if type == "string"
       then gsub("\\{\\{(?<name>[a-z_]+)\\}\\}"; ($vars[.name] // "") | tostring)
       else . end)
  | if ($vars.url // "") == "" then del(.actions) else . end
' "$template")

payload=$(jq -n --argjson card "$card" '{
  type: "message",
  attachments: [{contentType: "application/vnd.microsoft.card.adaptive", content: $card}]
}')

if [[ -z "${TEAMS_WEBHOOK_URL:-}" ]]; then
  echo "::warning::沒有設定 TEAMS_WEBHOOK_URL，只印出卡片內容"
  echo "$payload"
  exit 0
fi

curl -sS --fail-with-body -X POST -H "Content-Type: application/json" \
  --data "$payload" "$TEAMS_WEBHOOK_URL" >/dev/null
echo "已發送 Teams 卡片：$(jq -r '.body[0].text' <<<"$card")"
