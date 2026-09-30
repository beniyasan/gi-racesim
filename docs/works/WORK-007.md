# WORK-007 — 学習用レースセットと固定manifestを作る

状態: 未着手
担当案: Codex
前提: WORK-003, WORK-006

## 目的

取得数ではなく、発走前Xと展開Yを作れるレース数を把握する。

## 成果物

- packages/engine/src/gi_racesim/datasets/
- ローカルdatasets/manifest
- 品質集計

## 変更範囲

- packages/engine/src/gi_racesim/datasets/
- packages/engine/src/gi_racesim/normalization/
- packages/engine/tests/
- docs/data/

## 実施内容

- レース全頭を単位に、過去履歴とラップ/隊列教師を別領域にする。
- 最大12走/1096日など既存初期設定を版管理し、真の実績不足と取得不足を分ける。
- コーナー部分観測、群の統合、括弧内の内外と前後を取り違えない検査を追加する。
- 未来情報、結果表の行順、現在の生涯集計がXへ入らないテストを行う。
- source hash、parser version、features version、分割IDを固定する。全取得待ちにせず、検査済みセットから作る。

## 完了条件

- 少なくとも1レースのX/Yを原データと突き合わせて説明できる。
- 時点不明・欠測を0で埋めていない。
- 同じmanifestから同じ学習データを再生成できる。
- 実データ版はGitではなくローカル保存。コードには形式と合成例だけ。

## 今回しないこと

- まだない実績の創作
- 勝率を主ラベルにすること
- 評価レースの未来結果を入力にすること

## 完了報告

変更ファイル、実行コマンド、実測の結果、未実施、残課題、PR、収集/公開/常駐操作の有無を記録する。Doneは証拠を確認してから。
