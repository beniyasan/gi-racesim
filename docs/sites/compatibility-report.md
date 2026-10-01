# Sites互換性・本人限定検査レポート（WORK-002）

最終更新: 2026-10-01

このレポートは、`apps/site`のローカル検査と、ChatGPT Sitesで実機確認すべき項目を
分けて記録します。未実施を完了とは扱いません。

## 現在のソース

| 項目 | 値 |
| --- | --- |
| 起点 | `origin/main` のマージ済みコミット `ae7cefe` |
| Siteソース | `apps/site/` |
| 共有契約 | `contracts/viewer/v1/` |
| 配布物 | `scripts/site/package.py` のallowlist出力（未作成） |
| 実データ | 使用していない。合成fixtureのみ |

## ローカル確認

| 確認項目 | 結果 | 証拠 |
| --- | --- | --- |
| 静的HTTPでの相対パス | 確認済み | `apps/site/tests/assets.test.mjs` |
| 契約fixtureの検証 | 確認済み | `apps/site/tests/validator.test.mjs` |
| スキーマとfixtureの同期 | 確認済み | `apps/site/tests/assets.test.mjs` |
| 入力上限とHTMLエスケープ | コード確認済み | `apps/site/src/app.js` |
| Site作成・保存・デプロイ | 未実施 | Sitesアカウントの実機操作待ち |

## Sites実機マトリクス

| 項目 | 状態 | 証拠・次の入力 |
| --- | --- | --- |
| `apps/site`をローカルソースとして扱える | 未実施 | Sitesの作成画面で確認 |
| 作成後のプレビュー | 未実施 | 合成fixtureの表示を記録 |
| Siteの保存版とsource SHAの対応 | 未実施 | manifestと保存版を記録 |
| 所有者のみ／workspace管理者のアクセス | 未実施 | Share設定と実表示 |
| 未ログインの拒否 | 未実施 | ログイン誘導または実HTTP応答 |
| 権限のないアカウントの拒否 | 未実施 | 別アカウントで画面・ファイル・APIを検査 |
| 合成JSONの再訪後の保持 | 未実施 | run_idと入力SHAを照合 |
| コード更新後のデータ保持 | 未実施 | Site版とデータ版を分けて記録 |
| D1/R2または代替保存経路 | 未実施 | UIで確認できた経路だけ採用 |

## 判定

ローカルビューアと契約検証は再現可能ですが、WORK-002の完了条件であるSitesの
作成・保存・本人限定・再訪はまだ満たしていません。UIに存在しないCLI/APIを追加せず、
本人がSitesの実機操作を行った後にこのレポートを更新します。
