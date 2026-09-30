# WORK-008 — 基準予測・展開評価・結果exportを通す

状態: 未着手
担当案: Codex（Claude Codeレビュー）
前提: WORK-007

## 目的

高度なモデルより先に、何を改善したと判定するかを実装する。

## 成果物

- packages/engine/src/gi_racesim/evaluation/
- packages/engine/src/gi_racesim/exporter/
- ローカルbaseline run

## 変更範囲

- packages/engine/src/gi_racesim/models/
- packages/engine/src/gi_racesim/evaluation/
- packages/engine/src/gi_racesim/exporter/
- packages/engine/tests/
- docs/research/

## 実施内容

- 条件別の基準ラップ/隊列予測を、学習期間データだけで作る。
- 主評価を区間ラップ分布と前/同群/後の関係にし、観測される間隔・内外・カバレッジも出す。
- レース/時系列単位の分割と同じmanifestでの比較を実装する。大量試行のbest-ofだけを主評価にしない。
- 契約v1のviewer bundleを書き出す。baseline、retrospective等のラベルを落とさない。
- 実データが少ない場合は検証不足を出し、良いスコアが出るまで対象レースを選び直さない。

## 完了条件

- 同じ入力とseedから同じ基準結果・評価・exportが再現する。
- 正解のコーナーやラップを発走前生成へ混ぜない。
- 結果が悪くても未評価でも正しく表示する。
- 出力がWORK-003の検証器を通る。

## 今回しないこと

- ニューラルネット優位の宣言
- 回収率/Tierの最適化

## 完了報告

変更ファイル、実行コマンド、実測の結果、未実施、残課題、PR、収集/公開/常駐操作の有無を記録する。Doneは証拠を確認してから。
