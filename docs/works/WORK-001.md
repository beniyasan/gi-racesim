# WORK-001 — 非公開モノレポの土台と検査

状態: 部分完了（レビュー待ち、公開範囲の確認待ち）
担当案: Codex
前提: WORK-000

## 目的

サイト、Python処理、共有仕様を一つのコードベースで管理できる状態にする。

モノレポのフォルダー、共通指示、オフラインCI、Pythonエンジン、合成
fixture、ローカルビューアを実装した。GitHubのリポジトリ可視性は作業開始時
にPublicと確認されており、計画のPrivate要件はGitHub側で別途確認する。

## 成果物

- README.md
- AGENTS.md
- CLAUDE.md
- docs/adr/0001-private-monorepo.md
- .github/workflows/checks.yml
- .gitignore

## 変更範囲

- README.md
- AGENTS.md
- CLAUDE.md
- .github/
- .gitignore
- docs/adr/
- apps/site/
- packages/engine/
- contracts/
- ops/macos/

## 実施内容

- 名称案gi-racesim。GitHub作成時は本人の明示操作でPrivateにする。既存リポジトリがあれば勝手に置き換えない。
- apps/site、packages/engine、contracts、ops/macosを作る。PythonとJavaScriptの依存を分ける。
- v3から必要なコードを移し、監査結果に基づく回帰検査を残す。旧設計全体を実装済み扱いにしない。
- PRでPython検査・Siteビルド・契約検査を行う枠を作る。未実装チェックを成功したと偽装しない。
- CIには実取得・本番データ・公開認証を渡さない。初期は軽い検査を全PRで走らせる。
- GitHubの利用プランを確認し、利用可能ならmainの必須チェック/保護を設定。利用不可でもPrivateは維持し手動レビュー運用にする。

## 完了条件

- 再cloneした作業環境から、現在実装されているオフラインテストが再現する。
- 実DB・原HTML・秘密・学習重みが追跡対象でない。
- .githubに定期スクレイピング、収集用self-hosted runner、自動Sites公開がない。

## 今回しないこと

- 本番台帳のGit管理
- Sites一般公開
- 巨大なモノレポ専用基盤の導入

## 完了報告

変更ファイル、実行コマンド、実測の結果、未実施、残課題、PR、収集/公開/常駐操作の有無を記録する。Doneは証拠を確認してから。
