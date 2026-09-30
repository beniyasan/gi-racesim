# WORK-004 — Mac収集器の通信接続と運用コマンドをモックで検査

状態: モック検査済み（実ページの構造確認・LaunchAgent登録待ち）
担当案: Codex（Claude Codeレビュー）
前提: WORK-001

## 目的

既存台帳を迂回する通信がないMac用収集器を作る。

v3の永続ゲートと回帰テストをモノレポへ移し、差し替え可能なtransport、CLI、
原HTML/メタデータ保存を追加した。外部HTTPは明示opt-inでも実ページの構造確認前は
隔離され、LaunchAgentはテンプレートのみなので、実取得を開始できる状態ではない。

## 成果物

- packages/engine/src/gi_racesim/collector/
- ops/macos/LaunchAgentテンプレート
- docs/runbooks/collector.md

## 変更範囲

- packages/engine/src/gi_racesim/collector/
- packages/engine/tests/
- ops/macos/
- docs/runbooks/

## 実施内容

- status、tick、pause、resume、parse-cache等のCLI仕様を定義し、tickは最大1通信とする。
- 並列1・応答後120秒・5要求後3600秒・JST8〜22時・暦日と24時間各60要求を、同じsource_group台帳で強制する。
- 一覧、robots、失敗、retry、redirectも全て台帳を経由させる。ブラウザの隠れた並列要求を導入しない。
- 403/429/認証/challenge/構造変化で停止、失敗時の待機、時計逆行、activeが残ったクラッシュを検査する。
- コードcheckoutと本番実行環境を分け、launchdは承認済み版だけを参照する。開発worktreeの編集で本番が変わらない。
- 本番DBと原HTMLはApplication Support配下。モックは一時DBを使い、本番のパスへ接続しない。

## 完了条件

- 再起動・二重起動・日付変更・スリープ相当の時刻ジャンプでも上限を突破しない。
- 日次予算リセットや待機を無視したresumeを実装していない。
- HTTPアダプター内の自動リトライ/リダイレクトが台帳を迂回しない。
- 初期設定で外部収集を開始せず、LaunchAgentも自動登録しない。

## 今回しないこと

- 実サイトの取得
- 取得高速化
- 開発エージェントからの独立クローラ

## 完了報告

変更ファイル、実行コマンド、実測の結果、未実施、残課題、PR、収集/公開/常駐操作の有無を記録する。Doneは証拠を確認してから。
