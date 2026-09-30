# WORK-003 — Mac→Sitesのデータ契約v1を固定

状態: 実装済み（レビュー待ち）
担当案: Codex（Sites担当レビュー）
前提: WORK-001

## 目的

収集・モデル・Siteを別々に進めても接続が壊れない共通形式を作る。

契約v1、5 MiB上限、Python/ブラウザの検証器、合成fixture、原子書き出しを
追加した。自動同期と実Siteの保存・認可はWORK-002/005で確認する。

## 成果物

- contracts/viewer/v1/schema.json
- contracts/viewer/v1/fixtures/
- docs/contracts/viewer-v1.md

## 変更範囲

- contracts/
- packages/engine/src/gi_racesim/exporter/
- apps/site/の検証器
- docs/contracts/

## 実施内容

- schema_version、run_id、race_id、as_of、generated_at、producer_code_commit、dataset_id、model_id、originを定義する。
- originはsynthetic/baseline/model等の生成由来とprospective/retrospectiveの時点条件を区別する。実測は別セクションにする。
- ラップの区間長/単位、馬番と馬ID、馬群・間隔・内外・欠測・代表試行の表現を定義する。
- PythonとSite側の両方で同じ正常/異常fixtureを検証する。正確な馬群内前後順位を架空に埋めない。
- v1はUTF-8 JSONの手動取込、上限5 MiBを試験用設定にする。全試行の集計と代表試行最大20件を基本とし、件数上限はWORK-002の測定に基づき調整する。
- 未知のschema_versionは拒否、同run_id+同hashは再取込不要、同run_id+別hashは衝突として拒否する。

## 完了条件

- 同じfixtureがPythonとSiteの双方で一致して許可/拒否される。
- 秒と馬身区分、unknownと0、生成値と実測を区別できる。
- XSS的文字列はデータとして描画され実行されない。任意URL取得・スクリプト実行・pickle読込を行わない。
- 標本数全体と代表試行数が区別され、代表だけから全体の確率を計算しない。

## 今回しないこと

- 生HTMLのアップロード
- 重みファイルのアップロード
- 勝率/Tier中心への変更

## 完了報告

変更ファイル、実行コマンド、実測の結果、未実施、残課題、PR、収集/公開/常駐操作の有無を記録する。Doneは証拠を確認してから。
