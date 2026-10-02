# Sites互換性・本人限定検査レポート（WORK-002）

最終更新: 2026-10-02

このレポートは、`apps/site`のローカル検査と、ChatGPT Sitesで実機確認すべき項目を
分けて記録します。未実施を完了とは扱いません。

## 現在のソース

| 項目 | 値 |
| --- | --- |
| 起点 | Sites実機確認に使った作業コミット `8cbc2740cce8b9d082028a10a04a7d6fefcbd756` |
| Siteソース | `apps/site/` |
| 共有契約 | `contracts/viewer/v1/` |
| 配布物 | `/private/tmp/gi-racesim-site-package-1790935136`（source SHA `8cbc2740...`、package SHA `82110a33...`） |
| 実データ | 使用していない。合成fixtureのみ |

## ローカル確認

| 確認項目 | 結果 | 証拠 |
| --- | --- | --- |
| 静的HTTPでの相対パス | 確認済み | `apps/site/tests/assets.test.mjs` |
| 契約fixtureの検証 | 確認済み | `apps/site/tests/validator.test.mjs` |
| スキーマとfixtureの同期 | 確認済み | `apps/site/tests/assets.test.mjs` |
| 入力上限とHTMLエスケープ | コード確認済み | `apps/site/src/app.js` |
| Site作成・保存 | 確認済み | 合成fixtureを入力した本人限定の下書きversion 2 |
| Siteデプロイ | 未実施 | 公開URL・本番デプロイURLは発行していない |

## Sites実機マトリクス

| 項目 | 状態 | 証拠・次の入力 |
| --- | --- | --- |
| `apps/site`をローカルソースとして扱える | 未実施 | UIにはallowlist packageの取込経路を確認できず、合成fixtureを会話へ入力 |
| 作成後のプレビュー | 確認済み | 保存された`index.html`の非公開sandboxプレビューを表示 |
| Siteの保存版とsource SHAの対応 | 未実施 | Siteへローカルpackageを取り込んだ証拠はない |
| 所有者のみ／workspace管理者のアクセス | 部分確認 | UI表示は「本人のみの非公開」。別アカウント検査は未実施 |
| 未ログインの拒否 | 未実施 | ログイン誘導または実HTTP応答 |
| 権限のないアカウントの拒否 | 未実施 | 別アカウントで画面・ファイル・APIを検査 |
| 合成JSONの再訪後の保持 | 確認済み | `run-synthetic-001`、fixture SHA `9070dd48...`、同一内容を閉じて再表示 |
| コード更新後のデータ保持 | 未実施 | Site版とデータ版を分けて記録 |
| D1/R2または代替保存経路 | 未実施 | UIで確認できた経路だけ採用 |

## 実機確認記録（2026-10-02）

ChatGPT WorkのSitesで、`origin=synthetic`の合成fixtureを会話入力し、GIRaceSimの
下書きversion 2を保存した。保存版の`index.html`を開くと、レース概要、出走馬、
200〜1600mの`lap_quantiles`、3C/4Cの内外順序、`quality.missing_fields`と注記が
表示された。画面には「実測・学習結果・予測精度を表さない」「外部から取得した実データは
含まれない」と表示される。

一度ビューアを閉じ、同じ下書きの「index.htmlのプレビューを開く」から再表示した。
2回目も同じrun_id、ラップ表、3C/4C、品質注記が表示されたため、今回の確認範囲である
合成fixtureの保存前プレビューと再訪は確認済みとする。Sites内部のインタラクティブ
プレビュー基盤はサンドボックス制限で起動できなかったため、確認したのは保存版HTMLの
非公開sandboxプレビューである。

公開URLは発行していない。公開、デプロイ、共有範囲変更、外部サイト接続、実データ投入は
行っていない。`apps/site`のローカルソースまたはallowlist packageとSite保存版の対応、
未ログイン・別アカウントの拒否、D1/R2等の永続化経路は未確認のままとする。

## 判定

ローカルビューアと契約検証に加え、WORK-002の今回の確認範囲（合成fixtureを使った
本人限定の保存版プレビューと再訪）は完了した。公開前のアクセス境界とソース/package
対応は別検査として残る。UIに存在しないCLI/APIは追加していない。
