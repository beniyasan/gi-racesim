# Sites互換性・本人限定検査レポート（WORK-002）

最終更新: 2026-10-03

ローカル検査、Sitesの保存版作成、未実施の実デプロイ検査を分けて記録する。
保存版を作成できたことだけで、公開・アクセス拒否・永続化を完了扱いにしない。

## 現在のソース

| 項目 | 値 |
| --- | --- |
| 起点Gitコミット | `b105f91fd6980eb4122131981556f0fd0f320cf6` |
| Siteソース | `apps/site/` の許可リスト8ファイル（worker/storageはSite runtime側） |
| Site runtime | `src/worker.js`、`src/storage.js`、`drizzle/0001_viewer_runs.sql`、D1 `DB`・R2 `BUCKET` 宣言 |
| 共有契約 | `contracts/viewer/v1/` |
| ローカルmanifest | `GIRACESIM_SITE_MANIFEST.json`、format `gi-racesim-site-package/v1` |
| package SHA-256 | `21db4e5baf3b1a93360b41cf03ae5648b0b2377c61fc8d3a9de489333d27b8d0` |
| fixture SHA-256 | `9070dd48ab3fcbb21fb5da44d3af53235212b69ee3c634d20af4b5afbdb35845` |
| 実データ | 使用していない。合成fixtureのみ |

## ローカル確認

| 確認項目 | 結果 | 証拠 |
| --- | --- | --- |
| 静的HTTPでの相対パス | 確認済み | `apps/site/tests/assets.test.mjs` |
| 契約fixtureの検証 | 確認済み | `apps/site/tests/validator.test.mjs` |
| 入力上限とHTMLエスケープ | 確認済み | `apps/site/src/app.js` |
| 入力バイト列SHA-256 | 確認済み | `apps/site/src/content-hash.js`, `tests/content-hash.test.mjs` |
| Site配布物 | 確認済み | 上記起点コミットから許可リストを再生成 |

## Sites実機マトリクス

| 項目 | 状態 | 証拠・限界 |
| --- | --- | --- |
| `apps/site`をSite配布物へ取り込む | 確認済み | version 3で静的ソースをpushしたコミット `1e6abadb36d81516785c77793123f479a16aba64`、version 4でWorker成果物をpushしたコミット `67cd1745bff7b437c8199f7d785dc2e0ceb65d7c` |
| 保存版とsource SHAの対応 | 確認済み | version 3（静的）、source `1e6abadb36d81516785c77793123f479a16aba64`。version 4（Worker）、source `67cd1745bff7b437c8199f7d785dc2e0ceb65d7c`。version 5（migration含む）、source `1a4e815fce22dae4af7fb8b20747500d8857cb8c` |
| 保存版アーカイブ | 確認済み | version 3: `sha256:ccb91e0f1f05aac933935cc1198a987f252ba6f4f9d2614b3812a72b03d54cb3`、8 files、40960 bytes。version 4: `sha256:8eec5e54c26a60c9c2f2b2f1e51335d6991a787e601c9a613b0a6079b7bb84bb`、13 files、51200 bytes。version 5: `sha256:2237395c5aefcb6dcaa56c00bf4ac6fa231c1acea8add70dcd3cf3aab4f5da40`、14 files、61440 bytes |
| Siteデプロイ | 未実施 | `deployment_id=null`、公開URLなし。明示的な公開禁止を維持 |
| 現在のアクセス設定 | APIで確認済み | `access_mode=custom`、owner 1名、external visitor 0、editor 0 |
| 所有者以外の画面・API・ファイル拒否 | 未実施 | 配信URLがないため実HTTP検査不可 |
| 未ログインの拒否 | 未実施 | 配信URLがないため実HTTP検査不可 |
| 合成JSONの再訪後の保存バイト列SHA一致 | 未実施 | 既存version 2の表示再訪は画面一致だけ。version 3は保存版でありデータ保存なし |
| コード更新後のデータ保持 | 未実施 | 配信・D1/R2保存がないため不可 |
| D1/R2または代替保存経路 | コードとモック検証済み、クラウド実機未実施 | version 5にD1 `DB`・R2 `BUCKET`、保存API、`drizzle/0001_viewer_runs.sql`を含めた。未deployのためSite上のDB読出しは未確認 |

## 実機確認記録

2026-10-02に、WorkのSitesで`origin=synthetic`のfixtureを入力した下書きversion 2を
保存し、非公開sandbox previewを閉じて同じ下書きを再表示した。画面内容は一致したが、
入力バイト列を再取得していないため、保存のハッシュ一致とは判定しない。

2026-10-03に、起点Gitコミットから`apps/site`の許可リストを一時checkoutへコピーし、
Sitesのsource repositoryへpushした。Sitesの保存版version 3を作成し、返却値でsource
commit、archive hash、file count、deployment_idを再取得した。これは保存版の実機確認で
あり、続けてD1/R2対応Workerを含むversion 4、D1 migrationを含むversion 5も保存した。いずれもデプロイや公開を行った記録ではない。ローカルビューアは入力したUTF-8バイト列を
SHA-256表示し、fixtureの既知値とテストで一致させる。

## 判定

ローカルビューア、バイト列ハッシュ、Sitesへの許可リストsource取り込み、source SHAと
保存版version 3/4/5の対応、owner-only設定値の取得、保存APIのモック検証までは完了した。公開URLがないため、
未ログイン・別アカウントの拒否、再訪前後の保存バイト列、コード更新後のD1/R2保持は
未確認である。明示された「Sitesの公開を行わない」境界を越えず、WORK-002全体を
Doneとは扱わない。
