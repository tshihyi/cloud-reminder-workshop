# 打造你的雲端小祕書：演唱會提醒小幫手

工作坊練習用 repo。登記想看的演唱會，GitHub Actions 每小時檢查一次，時間到了就發 Teams 提醒；資料有錯就停下來，改發警示。

```
⏰ 每小時／手動執行
  → ① check：檢查資料、挑出該提醒的場次
  → ② publish：發 🎫 開賣／🎤 演出提醒到 Teams
  → ⚠️ alert：資料有錯時發警示（看板和提醒都不發）
```

這是 MDP 每日排程鏈（ETL → dbt → 下游）的縮小版。

## 目錄

```
├── .github/workflows/concert-reminder.yml   # 主戰場：第 2、3 關的 TODO 在這裡
├── concerts/                                # 登記的演唱會，一場一個 json
├── scripts/
│   ├── check.sh                             # 驗證資料、挑出該提醒的場次
│   ├── publish.sh                           # 發提醒
│   └── teams.sh                             # 填卡片樣板、發到 Teams
├── templates/                               # Teams 卡片樣板（開賣／演出／警示）
└── site/index.html                          # 演唱會看板（GitHub Pages）
```

## 演唱會 json 格式

```json
{
  "artist": "Maroon 5",
  "venue": "高雄世運主場館",
  "shows": ["2027-01-24"],
  "platform": "拓元售票",
  "sale_at": "2026-08-14 12:00",
  "url": "https://tixcraft.com/..."
}
```

- `shows`：演出日期，可以有好幾天。知道開演時間就寫成 `"2027-01-09 18:00"`，卡片會一起顯示。
- `sale_at`：開賣時間（台北時間）。還沒公布就填 `null`，只會發演出提醒。
- `platform`、`url`：可以填 `null`。有 `url` 時，卡片會多一顆「前往購票」按鈕。

**缺值可以，錯值要擋。** 開賣時間填 `null` 是合法的；日期寫成 `2026-11-31` 就會被擋下來。

## 三個提醒時點

| 提醒 | 什麼時候 |
|---|---|
| 🎫 開賣前一天 | 開賣前 23～24 小時那一輪 |
| 🎫 開賣前 1 小時 | 開賣前 0～1 小時那一輪 |
| 🎤 演出前一天 | 演出前一天 09:00 那一輪 |

GitHub 排程可能延遲幾十分鐘，所以課堂上一律手動執行。

## 手動執行

Actions → concert-reminder → Run workflow：

- **假裝現在是**：填 `2026-09-16 12:00` 之類的時間，就能當場觸發提醒。
- **順便更新演唱會看板**：預設不勾，課堂上省下部署時間。

示範用的時間：

| 填這個時間 | 會收到 |
|---|---|
| `2026-08-13 12:00` | 🎫 明天 12:00 Maroon 5 開賣 |
| `2026-09-14 09:30` | 🎫 還有 1 小時，Bruno Mars 開賣 |
| `2026-12-11 09:00` | 🎤 明天 Stray Kids 演出 |

## 三關

1. **登記演唱會**：在 `concerts/` 新增一個 json，執行一次，看 check 變綠燈。
2. **時間到了，提醒我**：在 `publish` 加上 `needs: check`，用「假裝現在是」執行，Teams 跳出提醒。
3. **日期填錯了**：把某場的演出日改成 `2026-11-31`，check 失敗；把 `alert` 的 `if: false` 改成 `if: failure()`，Teams 跳出警示。修好資料後手動重跑。

解答分支：`solution-2`、`solution-3`。現場來不及就直接切過去。

## 設定

- **Environment `lab-env`**：secret `TEAMS_WEBHOOK_URL`（Teams Workflows 建立的 webhook 網址）。
- **Pages**：Settings → Pages → Source 選 **GitHub Actions**。

演出日期與場地以主辦單位公告為準。
