#!/usr/bin/env bash
# 檢查 concerts/*.json，挑出現在該提醒的場次。
# 資料有錯就 exit 1，讓下游的 publish 不要跑。
#
# 環境變數：
#   NOW  假裝現在是幾點（YYYY-MM-DD HH:MM，台北時間），留空＝現在
#
# 產出：
#   reminders.json   該提醒的場次
#   site/data.json   看板用的全部場次
set -euo pipefail

export TZ=Asia/Taipei
cd "$(dirname "$0")/.."

if [[ -n "${NOW:-}" ]]; then
  if ! now_epoch=$(date -d "$NOW" +%s 2>/dev/null); then
    echo "::error::NOW 格式不對：$NOW（要寫成 YYYY-MM-DD HH:MM）"
    exit 1
  fi
else
  now_epoch=$(date +%s)
fi
now_text=$(date -d "@$now_epoch" '+%Y-%m-%d %H:%M')
today=$(date -d "@$now_epoch" +%F)
hour=$(date -d "@$now_epoch" +%H)
echo "現在時間（台北）：$now_text"

error_count=0
report_error() {
  echo "::error file=$1::$2"
  error_count=$((error_count + 1))
}

# 日期要能被 date 認得，而且轉回來要一模一樣（2026-11-31 會被擋下）
is_valid_date() {
  [[ "$1" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] &&
    [[ "$(date -d "$1" +%F 2>/dev/null)" == "$1" ]]
}

is_valid_datetime() {
  [[ "$1" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\ [0-9]{2}:[0-9]{2}$ ]] &&
    [[ "$(date -d "$1" '+%Y-%m-%d %H:%M' 2>/dev/null)" == "$1" ]]
}

reminders='[]'
board='[]'

shopt -s nullglob
files=(concerts/*.json)
if [[ ${#files[@]} -eq 0 ]]; then
  echo "::warning::concerts/ 裡沒有任何演唱會"
fi

for file in "${files[@]}"; do
  if ! jq empty "$file" 2>/dev/null; then
    report_error "$file" "不是合法的 JSON"
    continue
  fi

  artist=$(jq -r '.artist // ""' "$file")
  venue=$(jq -r '.venue // ""' "$file")
  sale_at=$(jq -r '.sale_at // ""' "$file")
  url=$(jq -r '.url // ""' "$file")
  mapfile -t shows < <(jq -r '(.shows // [])[]' "$file")

  file_ok=true
  [[ -z "$artist" ]] && { report_error "$file" "缺少 artist（藝人）"; file_ok=false; }
  [[ -z "$venue" ]] && { report_error "$file" "缺少 venue（場地）"; file_ok=false; }
  [[ ${#shows[@]} -eq 0 ]] && { report_error "$file" "shows（演出日期）至少要有一天"; file_ok=false; }
  for show in "${shows[@]}"; do
    # 演出可以只寫日期，或加上開演時間
    is_valid_date "$show" || is_valid_datetime "$show" ||
      { report_error "$file" "演出日期不存在或格式不對：$show（要寫成 YYYY-MM-DD 或 YYYY-MM-DD HH:MM）"; file_ok=false; }
  done
  # 開賣時間還沒公布可以填 null，有填就要是對的
  if [[ -n "$sale_at" ]] && ! is_valid_datetime "$sale_at"; then
    report_error "$file" "開賣時間不存在或格式不對：$sale_at（要寫成 YYYY-MM-DD HH:MM）"
    file_ok=false
  fi
  if [[ -n "$url" && ! "$url" =~ ^https:// ]]; then
    report_error "$file" "售票連結要以 https:// 開頭：$url"
    file_ok=false
  fi
  [[ "$file_ok" == true ]] || continue

  concert=$(jq -c '{artist, venue, shows, platform: (.platform // null), sale_at: (.sale_at // null), url: (.url // null)}' "$file")
  board=$(jq -c --argjson concert "$concert" '. + [$concert]' <<<"$board")

  add_reminder() {
    reminders=$(jq -c --argjson concert "$concert" --arg type "$1" --arg show_date "${2:-}" \
      '. + [$concert + {type: $type, show_date: $show_date}]' <<<"$reminders")
  }

  # 排程每小時跑一次，所以每個提醒只看「一小時的窗口」
  if [[ -n "$sale_at" ]]; then
    seconds_left=$(($(date -d "$sale_at" +%s) - now_epoch))
    if ((seconds_left > 23 * 3600 && seconds_left <= 24 * 3600)); then
      add_reminder sale_1d
    elif ((seconds_left > 0 && seconds_left <= 3600)); then
      add_reminder sale_1h
    fi
  fi
  # 演出前一天早上 9 點那一輪提醒
  for show in "${shows[@]}"; do
    if [[ "$(date -d "${show:0:10} -1 day" +%F)" == "$today" && "$hour" == "09" ]]; then
      add_reminder show_1d "$show"
    fi
  done
done

mkdir -p site
jq --arg now "$now_text" '{generated_at: $now, concerts: .}' <<<"$board" >site/data.json
jq . <<<"$reminders" >reminders.json

reminder_count=$(jq length <<<"$reminders")
write_summary() {
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then cat >>"$GITHUB_STEP_SUMMARY"; else cat; fi
}
{
  echo "## 🎤 演唱會檢查結果"
  echo
  echo "- 現在時間（台北）：$now_text"
  echo "- 登記場次：$(jq length <<<"$board")"
  echo "- 該提醒：$reminder_count"
  echo "- 資料錯誤：$error_count"
  if ((reminder_count > 0)); then
    echo
    echo "| 提醒 | 藝人 | 場地 |"
    echo "|---|---|---|"
    jq -r '.[] | "| \(.type) | \(.artist) | \(.venue) |"' <<<"$reminders"
  fi
} | write_summary

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "reminders=$(jq -c . <<<"$reminders")" >>"$GITHUB_OUTPUT"
fi

if ((error_count > 0)); then
  echo "資料有 $error_count 個錯誤，看板和提醒都不發。"
  exit 1
fi
echo "檢查通過，該提醒 $reminder_count 筆。"
