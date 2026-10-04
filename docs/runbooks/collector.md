# 収集器のオフライン運用手順

この手順はWORK-004の合成fixture検査用です。既定のtransportは外部HTTPを
拒否し、`tick`は台帳が許可したときだけtransportを一度呼びます。失敗、
リダイレクト、再試行も同じSQLite台帳の要求枠を使います。

## モックで一周する

作業リポジトリのルートから一時ディレクトリを使います。本番の
`~/Library/Application Support/GIRaceSim/` や本番台帳をテストに指定しません。

```bash
export PYTHONPATH="$PWD/packages/engine/src"
RUN_DIR="$(mktemp -d)"
DB="$RUN_DIR/collector.sqlite3"
RAW="$RUN_DIR/raw"
NOW=2026-09-30T08:00:00+09:00
cat > "$RUN_DIR/page.html" <<'HTML'
<html><body>
<table data-giracesim="synthetic-result-v1">
  <tr><th data-field="horse">Horse</th><th data-field="finish">Finish</th></tr>
  <tr><td data-field="horse">Synthetic A</td><td data-field="finish">1</td></tr>
</table>
</body></html>
HTML

python3 -m gi_racesim.collector --db "$DB" --cache-dir "$RAW" \
  --now "$NOW" approve --note 'synthetic source review'
python3 -m gi_racesim.collector --db "$DB" --cache-dir "$RAW" \
  --now "$NOW" enqueue https://race.netkeiba.com/mock/1 \
  --discovered-from synthetic-fixture
python3 -m gi_racesim.collector --db "$DB" --cache-dir "$RAW" \
  --now "$NOW" tick --mock-html "$RUN_DIR/page.html"
python3 -m gi_racesim.collector --db "$DB" --cache-dir "$RAW" parse-cache
python3 -m gi_racesim.collector --db "$DB" --cache-dir "$RAW" status
```

`tick`の結果に`transport_calls: 1`と`raw_ref`が出ます。`parse-cache`は保存済み
HTMLと台帳メタデータだけを読み、HTTPを呼びません。保存されたHTMLとJSON sidecar
は`$RAW`に作られ、SQLiteの`response`行から要求URL、応答URL、時刻、status、
headers、SHA-256、ファイルパスを辿れます。

CLIのmock tickは`synthetic-result-v1`の結果表と`horse`・`finish`の見出し／データセルを
検査します。表や列が消えた場合は、HTMLを保存してタスクを`QUARANTINED`、source groupを
`parse_schema_review`にします。単に`html`・`body`・`table`があるだけでは成功しません。

実ページの検証器はWORK-006で原表との照合後に接続します。それまでは外部tickの未知の
2xx応答も保存・隔離して停止します。合成fixture用の検証器を実ページには使いません。
`parse-cache`は汎用のtitle/text抽出であり、`PARSED`は実レースデータの採用を意味しません。

保存済みのnetkeiba出馬表をレビュー済みのsource adapterで確認する場合は、次のように
台帳のSHA-256とURLを検査してから正規化結果を標準出力へ返します。これは保存ファイルだけを
読み、要求枠を消費せず、外部HTTPを呼びません。

```bash
python3 -m gi_racesim.collector --db "$DB" --cache-dir "$RAW" \
  parse-cache --adapter netkeiba-shutuba --ref 'cache:TOKEN'
```

構造不一致、race ID不一致、保存バイト列のSHA不一致は `PARSE_ERROR` または
`HASH_MISMATCH` として採用しません。出馬表にない結果・ラップ・コーナーを補完しません。

## 状態確認と停止・再開

```bash
python3 -m gi_racesim.collector --db "$DB" --cache-dir "$RAW" status
python3 -m gi_racesim.collector --db "$DB" --cache-dir "$RAW" \
  --now 2026-09-30T08:03:00+09:00 pause --note 'manual source review'
python3 -m gi_racesim.collector --db "$DB" --cache-dir "$RAW" \
  --now 2026-09-30T08:04:00+09:00 resume --note 'review complete'
```

`resume`は`batch_used`、日次/24時間の要求数、`next_at`を変更しません。active
tokenが残っている場合はpause/resumeで解除できません。まずworkerが停止している
ことを確認し、要求の結果が不明なら手動で`abandoned`として保守復旧します。
その要求を成功扱いにしたり、待機・予算をリセットしたりしません。

active tokenの保守復旧は、worker停止を確認した後に一度だけ実行します。`status`で
tokenを確認し、`abandon`へ明示的に渡します。

```bash
export NOW=2026-09-30T08:10:00+09:00
TOKEN='実際のstatus出力にあるactive_token'
python3 -m gi_racesim.collector --db "$DB" --cache-dir "$RAW" \
  --now "$NOW" abandon --token "$TOKEN" --note 'worker stopped; response uncertain'
```

この操作は要求を`UNCERTAIN`にしてsource groupをpauseします。再開する場合も、
原因と証拠をnoteに残した`resume`を本人が行います。

## transportの境界

`--mock-html`はローカルfixture専用です。通常の`tick`は
`EXTERNAL_DISABLED`を返し、要求枠を消費せず、ソケットも開きません。
`--allow-external`は、レビュー済みの実行版で別途本人が明示的に有効化するための
opt-inです。`UrllibTransport`は自動retryとredirect追従を持たず、403/429、認証要求、
challenge、アクセス制限をsource-wide pauseへ送ります。構造変更は
`Collector(response_parser=...)`のparserが例外を返した場合に同じ
`parse_schema_review` pauseになります。外部tickに`--now`を指定することは禁止し、
要求開始と応答終了で実際の壁時計を読みます。ライブラリの外部transportも`tick(now=...)`と
`now_fn`注入を拒否します。応答中の時刻逆行はactive tokenを残して保守確認へ止めます。
`--allow-external`と`--mock-html`も同時指定できません。テストでは外部経路を検査する場合も
HTTPをモックに差し替え、実サイトへ通信しません。

認証／challengeはstatusや応答URLの分類に先立って判定します。例えば302と
`WWW-Authenticate`の組み合わせもsource-wide pauseになり、後続タスクを実行しません。
本文の一般的なCDN名だけではアクセス制限と判定しません。captcha、access denied、
challenge用マーカー、認証系ヘッダーなど明示的な停止根拠がある場合だけsource-wide pauseにします。

## LaunchAgentテンプレート

`ops/macos/com.giracesim.collector.plist.template`は登録前の雛形です。
`USERNAME`と`CHECKED_OUT_ENGINE`をレビュー済みのimmutable checkoutへ置換し、
`plutil -lint`で構文を確認します。テンプレートには`--allow-external`がなく、
この作業では`launchctl bootstrap`、`enable`、`kickstart`を実行しません。
登録・有効化は、台帳バックアップ、active token確認、実行版レビューを済ませた
本人操作として別に行います。

## 検査

```bash
PYTHONPATH=packages/engine/src python3 -m unittest discover \
  -s packages/engine/tests -v
python3 -m unittest discover -s scripts/tests -v
python3 scripts/check_tracked_files.py
```

この検査は一時SQLiteと合成fixtureだけを使います。実サイト取得、LaunchAgent登録、
本番台帳接続、Sites公開、モデル学習は含みません。
