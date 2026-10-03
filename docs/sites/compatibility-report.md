# Sites互換性・本人限定検査レポート（WORK-002）

最終更新: 2026-10-03

ローカル検査、Sitesの保存版作成、未実施の実デプロイ検査を分けて記録する。
保存版を作成できたことだけで、公開・アクセス拒否・永続化を完了扱いにしない。

## 現在のソース

| 項目 | 値 |
| --- | --- |
| 起点Gitコミット | `239031fd5eda45ec88f1bb34bf54b984bc0e9c2f` |
| Siteソース | `apps/site/` の許可リスト8ファイル（worker/storageはSite runtime側） |
| Site runtime | `src/worker.js`、`src/storage.js`、`drizzle/0001_viewer_runs.sql`、D1 `DB`・R2 `BUCKET` 宣言 |
| 共有契約 | `contracts/viewer/v1/` |
| ローカルmanifest | `GIRACESIM_SITE_MANIFEST.json`、format `gi-racesim-site-package/v1` |
| package SHA-256 | `6e0e561a55bf61f1738b0bfeadf04e3b66807fcb9ca3a422b482540d556d434a` |
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
| 保存版とsource SHAの対応 | 確認済み | version 3（静的）、source `1e6abadb36d81516785c77793123f479a16aba64`。version 4（Worker）、source `67cd1745bff7b437c8199f7d785dc2e0ceb65d7c`。version 5（migration含む）、source `1a4e815fce22dae4af7fb8b20747500d8857cb8c`。version 6（認証判定修正後）、source `e109a272b63b1b8e0434c6100d57c07659ea4817` |
| 保存版アーカイブ | 確認済み | version 3: `sha256:ccb91e0f1f05aac933935cc1198a987f252ba6f4f9d2614b3812a72b03d54cb3`、8 files、40960 bytes。version 4: `sha256:8eec5e54c26a60c9c2f2b2f1e51335d6991a787e601c9a613b0a6079b7bb84bb`、13 files、51200 bytes。version 5: `sha256:2237395c5aefcb6dcaa56c00bf4ac6fa231c1acea8add70dcd3cf3aab4f5da40`、14 files、61440 bytes。version 6: `sha256:7bf8c86101428b7dd1e825bdcb9f8c002b1f9cdb8a3ff9f3f456d2d991af4b7f`、14 files、61440 bytes |
| Siteデプロイ | 確認済み | 本番URL `https://giracesim-viewer.beniya.chatgpt.site`、version 9、source `7b52b48d44ad65e03b4b222dc4a935010c6265da`、archive `sha256:8d800b78d0710de6d65d6ad15535e78101b6a659d3183b162a101e48831a754b`、16 files、102400 bytes、deployment succeeded |
| 現在のアクセス設定 | APIで確認済み | `access_mode=custom`、owner 1名、external visitor 0、editor 0 |
| 未ログインの拒否 | 確認済み | 公開URLへのcurlで画面、API、fixtureの各経路がHTTP 401。Chrome所有者セッションではビューアーを表示 |
| 所有者のfixture表示 | 確認済み | Chromeで合成fixtureを表示し、既知の入力SHA-256を表示 |
| 合成JSONの保存・再訪後の保存バイト列SHA一致 | 確認済み | Owner UIの「Siteへ保存して再読込」でD1/R2へ保存後、`保存・再読込済み`と既知SHAを表示。D1 `viewer_runs` 1行、4993 bytes |
| コード更新後のデータ保持 | 確認済み | version 9へ更新後、「保存済みを再読込」で再保存せず同じSHAを表示 |
| D1/R2または代替保存経路 | 確認済み | `DB.viewer_runs`のowner/run/hash/object_key/byte_lengthを取得。R2原文の再ハッシュ検証はWorker実装とUI再読込で確認 |

## 実機確認記録

2026-10-02に、WorkのSitesで`origin=synthetic`のfixtureを入力した下書きversion 2を
保存し、非公開sandbox previewを閉じて同じ下書きを再表示した。画面内容は一致したが、
入力バイト列を再取得していないため、保存のハッシュ一致とは判定しない。

2026-10-03に、起点Gitコミットから`apps/site`の許可リストを一時checkoutへコピーし、
Sitesのsource repositoryへpushした。Sitesの保存版version 3を作成し、返却値でsource
commit、archive hash、file count、deployment_idを再取得した。これは保存版の実機確認で
あり、続けてD1/R2対応Workerを含むversion 4、D1 migrationを含むversion 5、認証判定修正後のversion 6も保存した。いずれもデプロイや公開を行った記録ではない。ローカルビューアは入力したUTF-8バイト列を
SHA-256表示し、fixtureの既知値とテストで一致させる。

2026-10-03に、Worker実行環境に静的`ASSETS` bindingが無い場合でも配信できるよう、
許可リストのUTF-8資産をWorkerアーカイブへ埋め込む生成器を追加した。初回のWorker公開で
確認されたroot 404を、生成Workerのroot/HEAD/405/未認証API/未知経路テストと再デプロイで
解消し、Chrome所有者セッションでrootとfixture表示を確認した。続くversion 9では保存・
再読込ボタンを追加し、合成fixtureを保存した後にD1の1行（4993 bytes、既知SHA）を確認した。
version 9へ更新した後、保存済みを再読込するだけで同じSHAが表示されることも確認した。

## 判定

ローカルビューア、バイト列ハッシュ、Sitesへの許可リストsource取り込み、Worker静的資産
フォールバック、owner-only設定値、未ログイン401、合成fixtureのD1/R2保存・再読込、
コード更新後の保持まで確認した。別アカウントでのログイン拒否は、この所有者限定環境で
別アカウント資格情報を用意していないため未実施である。実データ・実取得・LaunchAgentは
使用していない。
