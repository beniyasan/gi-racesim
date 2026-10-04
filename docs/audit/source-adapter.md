# WORK-006 source adapter audit

状態: 初回実取得済み（3要求、source groupはアクセス制限のため停止中）

この記録は、少量実取得を開始する前に対象と保存境界を固定するためのものです。
対象URLや利用条件を推測して埋めず、本人が開始した要求だけを本番台帳へ登録します。
直接の `curl`、ブラウザ閲覧、台帳を迂回する検査は実取得の証拠にしません。

## 対象

| 項目 | 記録 |
| --- | --- |
| source group | `netkeiba.com`（全サブドメイン共通。変更には明示的なレビューが必要） |
| 最初の公開入口URL | `https://race.netkeiba.com/race/shutuba.html?race_id=202605040211`（本人指定、2026-10-03） |
| 対象レース／ID | `202605040211` |
| 利用条件の確認日・根拠 | 未確認。実取得の採用判断は保留する |
| `robots.txt` の確認日・結果 | 2026-10-03、`https://race.netkeiba.com/robots.txt` はHTTP 404。robots不在を許可とは解釈しない |
| 必要フィールド | レース識別、開催日・競馬場・距離、結果、ラップ、コーナー隊列、欠測理由 |
| 人手照合者・照合日 | 未実施。出馬表の原表照合を記録する |

## 保存と台帳

- 本番SQLite台帳は `~/Library/Application Support/GIRaceSim/collector.sqlite3` を使う。
- 原HTMLとsidecarメタデータは `~/Library/Application Support/GIRaceSim/raw/` に保存する。
- normalizedデータは原HTMLと別の `~/Library/Application Support/GIRaceSim/normalized/` に置き、同じraw SHA-256で対応付ける。
- Gitには原HTML、sidecar、normalized実データを追加しない。テストは一時DB・一時raw・合成fixtureだけを使う。
- 実取得開始前に本番台帳とrawのバックアップ先、復旧方法、実行版の完全SHAを記録する。

## 少量取得の手順

1. 利用条件、公開範囲、`robots.txt`、必要フィールドを確認し、この文書とreview台帳へ記録する。
2. 本人が入口URLを `enqueue` し、同じsource groupの一つの台帳で管理する。
3. `tick` は一回につき最大1要求だけ実行する。原HTML保存とメタデータ記録が終わるまで完了扱いにしない。
4. 200応答でも未確認構造なら保存後に隔離し、パーサーを保存HTMLへ接続する。拒否画面、認証要求、403/429、構造変更はsource group全体を停止する。
5. 実測・失敗・隔離・不足と要求間隔を台帳から集計し、約30要求に到達したら本人が停止する。日次・直近24時間の60要求上限を超えない。
6. 保存HTMLを原表と人手照合し、各採用HTML形式の抽出テストを合成化してから、次の要求を再開する。

## 実取得の開始記録

| 項目 | 記録 |
| --- | --- |
| 開始操作をした本人 | 本人指定URLを受領したCodex実行（2026-10-03） |
| 開始日時（JST） | 2026-10-03 15:56:04 |
| 実行版完全SHA | `d625331ffa74eb50ecbf8468f29c9eb6ed400ad4`（parser適用前の取得版） |
| 本番台帳バックアップ | 新規台帳のため既存バックアップなし。以後の再開前に取得する |
| 初回task / URL | robots.txt、続いて `race_id=202605040211` |
| 停止日時・累計要求数 | 2026-10-04 21:25:49、3要求、`blocked` |

## 初回robots要求の実績

- 開始時刻: 2026-10-03 15:56 JST（実際の台帳時刻）
- URL: `https://race.netkeiba.com/robots.txt`
- 結果: HTTP 404 / `NOT_FOUND` / transport calls 1
- 保存参照: `cache:5ac94915cff34ada9a6547c3e48f8eb9`
- 保存サイズ・SHA-256: 196 bytes / `80c3fe2ae1062abf56456f52518bd670f9ec3917b7f85e152b347ac6b6faf880`
- 次回要求可能時刻: 応答終了後120秒以上。レース本文の取得後に利用条件と公開範囲を再確認する。

## 初回レースHTMLの実績

- 取得時刻: 2026-10-03 16:01 JST（台帳の応答終了時刻）
- URL: `https://race.netkeiba.com/race/shutuba.html?race_id=202605040211`
- 結果: HTTP 200 / `PARSE_ERROR` / transport calls 1。構造未確認のためsource groupを自動停止。
- 保存参照: `cache:0f7916d9c3f94837a789a81ec2897e7f`
- 保存サイズ・SHA-256: 287241 bytes / `9f3e8c6a483f837774d0d6ef0a14ccf0e21fddfe9b3124140e8ef5ad9a963e32`
- 保存HTMLから確認できた範囲: race_id `202605040211`、2026-10-04 東京11R、芝1800m、17頭の出馬表。これは発走前の出走表で、結果・実測ラップ・コーナー隊列ではない。
- ローカルparser適用結果: 17頭の出走表を抽出し、`~/Library/Application Support/GIRaceSim/normalized/202605040211__9f3e8c6a483f8377.json` に新規保存した。`results`、`laps`、`corners`、`odds_at_start` は欠測のまま。
- parser実装結果: 保存HTML専用の `netkeiba_shutuba_v1` と `parse-cache --adapter netkeiba-shutuba` を追加し、合成HTML 6テストと実HTML17行のローカル解析に成功した。source groupの `parse_schema_review` は利用条件・原表照合・レビュー済み実行版の確認まで解除しない。

## 初回過去走入口の実績

- 取得時刻: 2026-10-04 21:25 JST（台帳の応答終了時刻）
- URL: `https://db.netkeiba.com/horse/2019102632`（出馬表から最初に発見した過去走入口）
- 結果: HTTP 200 / `BLOCKED` / transport calls 1。応答本文にログイン・bot関連の文字列があり、認証要求またはアクセス制限の可能性を保守的に停止判定した。
- 保存参照: `cache:0da6f400b26b4a8094950f7ba7e9ac1b`
- 保存サイズ・SHA-256: 83402 bytes / `ad75630c8879cdaedcf37bfa36332b712cf9387ea44f15f3fde3e27889f0cbab`
- Content-Type: `text/html; charset=EUC-JP`。rawとsidecarは本番rawディレクトリへ保存したが、文字コード対応や本文の採用判断は未実施。
- 同じsource groupを `blocked` のまま停止し、自動retry、リダイレクト追跡、残りの馬・結果・ラップページの追加要求は行わない。

## 未実施・保留

- 利用条件・通常公開範囲の確認と、人手による原表照合。過去走入口はアクセス制限判定のため、解除条件を確認するまで再開しない。
- 結果・履歴・ラップ・コーナーの追加取得と、実HTMLパーサーをlive tickへ接続して再開すること。
- normalized出走表からWORK-003 bundleへ変換すること。出馬表だけではviewer結果bundleを作らない。
