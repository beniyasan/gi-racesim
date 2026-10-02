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
| 配布物 | `/private/tmp/gi-racesim-site-package-1790935136` |
| manifest | `GIRACESIM_SITE_MANIFEST.json`、format `gi-racesim-site-package/v1`、source_root `apps/site`、manifest SHA-256 `f322ccb7742c94b69e9ce722233dff181aaa24c0d662db94ad280582273762c1` |
| source SHA | `8cbc2740cce8b9d082028a10a04a7d6fefcbd756` |
| package SHA-256 | `82110a33ddc56d8dc024b4ee59cc39427d62509f20001d0fdc82be3b00defb9e` |
| fixture SHA-256 | `9070dd48ab3fcbb21fb5da44d3af53235212b69ee3c634d20af4b5afbdb35845` |
| 実データ | 使用していない。合成fixtureのみ |

## ローカル確認

| 確認項目 | 結果 | 証拠 |
| --- | --- | --- |
| 静的HTTPでの相対パス | 確認済み | `apps/site/tests/assets.test.mjs` |
| 契約fixtureの検証 | 確認済み | `apps/site/tests/validator.test.mjs` |
| スキーマとfixtureの同期 | 確認済み | `apps/site/tests/assets.test.mjs` |
| 入力上限とHTMLエスケープ | コード確認済み | `apps/site/src/app.js` |
| Site作成・保存 | 部分確認 | 合成fixtureだけを入力した下書きversion 2。`apps/site`/package取り込みとsource対応は未確認 |
| Siteデプロイ | 未実施 | 公開URL・本番デプロイURLは発行していない |

## Sites実機マトリクス

| 項目 | 状態 | 証拠・次の入力 |
| --- | --- | --- |
| `apps/site`をローカルソースとして扱える | 未実施 | UIにはallowlist packageの取込経路を確認できず、合成fixtureを会話へ入力 |
| 作成後のプレビュー | 確認済み | 保存された`index.html`の非公開sandboxプレビューを表示 |
| Siteの保存版とsource SHAの対応 | 未実施 | Siteへローカルpackageを取り込んだ証拠はない |
| 所有者のみ／workspace管理者のアクセス | 未確認 | UIの「本人のみの非公開」表示は確認したが、実際のアクセス境界は未検証 |
| 未ログインの拒否 | 未実施 | ログイン誘導または実HTTP応答 |
| 権限のないアカウントの拒否 | 未実施 | 別アカウントで画面・ファイル・APIを検査 |
| 合成JSONの再訪後の保持 | 未確認 | 表示内容は同じだったが、再訪後の保存バイト列SHAを取得していない |
| コード更新後のデータ保持 | 未実施 | Site版とデータ版を分けて記録 |
| D1/R2または代替保存経路 | 未実施 | UIで確認できた経路だけ採用 |

## 実機確認記録（2026-10-02）

ChatGPT WorkのSitesで、`origin=synthetic`の合成fixture（SHA-256
`9070dd48ab3fcbb21fb5da44d3af53235212b69ee3c634d20af4b5afbdb35845`）を会話入力し、
GIRaceSimの下書きversion 2を保存した。これはfixture入力からの下書き保存の確認であり、
`apps/site`またはallowlist packageの取り込みを確認したものではない。保存版の`index.html`を開くと、レース概要、出走馬、
200〜1600mの`lap_quantiles`、3C/4Cの内外順序、`quality.missing_fields`と注記が
表示された。画面には「実測・学習結果・予測精度を表さない」「外部から取得した実データは
含まれない」と表示される。

一度ビューアを閉じ、同じ下書きの「index.htmlのプレビューを開く」から再表示した。
2回目も同じrun_id、ラップ表、3C/4C、品質注記が表示された。ただし、再訪前後の
保存バイト列SHAは取得していないため、ハッシュ一致を含む保存受入条件は未確認とする。
Sites内部のインタラクティブ
プレビュー基盤はサンドボックス制限で起動できなかったため、確認したのは保存版HTMLの
非公開sandboxプレビューである。

公開URLは発行していない。公開、デプロイ、共有範囲変更、外部サイト接続、実データ投入は
行っていない。`apps/site`のローカルソースまたはallowlist packageとSite保存版の対応、
実際のアクセス境界、未ログイン・別アカウントの拒否、再訪前後のハッシュ一致、D1/R2等の
永続化経路は未確認のままとする。

## 判定

ローカルビューアと契約検証に加え、合成fixtureを会話入力した下書き保存と保存版HTMLの
視覚的なプレビュー／再訪は確認した。WORK-002の完了条件であるrepository source/package
取り込み、source SHAとSite版の対応、実際のアクセス境界、再訪前後のハッシュ一致、
永続化経路は未確認であり、WORK-002全体をDoneとは扱わない。UIに存在しないCLI/APIは
追加していない。
