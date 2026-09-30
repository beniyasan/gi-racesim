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
printf '<html><title>synthetic</title><body>fixture</body></html>\n' > "$RUN_DIR/page.html"

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
`parse_schema_review` pauseになります。WORK-004の検査ではこのflagを使わず、
実サイトへの取得を行いません。

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
