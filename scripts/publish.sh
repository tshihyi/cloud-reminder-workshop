#!/usr/bin/env bash
# 依 check 挑出的場次發 Teams 提醒。
#
# 環境變數：
#   REMINDERS          check 的輸出（JSON 陣列）
#   TEAMS_WEBHOOK_URL  Teams webhook 網址
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -z "${REMINDERS:-}" ]]; then
  echo "::warning::沒拿到 check 的結果。publish 是不是沒等 check 跑完就先跑了？（第 2 關）"
  exit 0
fi

count=$(jq length <<<"$REMINDERS")
if ((count == 0)); then
  echo "現在沒有要提醒的場次。"
  exit 0
fi

jq -c '.[]' <<<"$REMINDERS" | while read -r reminder; do
  type=$(jq -r .type <<<"$reminder")
  case "$type" in
    sale_1d)
      title="明天 $(jq -r '.sale_at[11:]' <<<"$reminder") $(jq -r .artist <<<"$reminder") 開賣"
      template=templates/sale-card.json ;;
    sale_1h)
      title="還有 1 小時，$(jq -r .artist <<<"$reminder") 開賣"
      template=templates/sale-card.json ;;
    show_1d)
      title=""
      template=templates/show-card.json ;;
    *)
      echo "::warning::不認得的提醒類型：$type"
      continue ;;
  esac
  variables=$(jq -c --arg title "$title" '. + {title: $title, platform: (.platform // "未公布")}' <<<"$reminder")
  bash scripts/teams.sh "$template" "$variables"
done
