# Sites公開経路の検査手順（WORK-002）

この手順は、`apps/site`を本人限定のChatGPT Siteへ持ち込む経路と、合成fixtureの保存契約を記録する。GitHub pushからSiteの公開は自動で始まらない。公開URLを発行しない検証では、Sitesの保存版までで止める。

## 1. Gitと配布物を固定する

レビュー済みコミットを起点に実行する。

```bash
git status --short
git rev-parse HEAD
python3 scripts/site/package.py --output /private/tmp/gi-racesim-site-package
cat /private/tmp/gi-racesim-site-package/GIRACESIM_SITE_MANIFEST.json
```

出力先が存在して中身がある場合、スクリプトは上書きせず停止する。manifestにはソースSHA、許可したファイルのサイズとSHA-256、配布物のSHA-256を残す。原HTML、SQLite、モデル、認証情報は配布物に含めない。

## 2. Sitesへ保存版を作る

Sitesの公式Work/Codex操作で既存Siteを開き、source repository write credentialを一時的に取得する。認証トークンはコマンド引数、ファイル、ログへ書かない。Site workflowへ標準入力で渡し、`commit_sha`とarchiveを保存する。

`sites_save_site_version`へ渡すのは、push済みsourceの完全SHAと同じsourceから作ったarchiveだけにする。保存後は`sites_get_site_version`で次を再取得する。

- Site version numberとversion ID
- source commit SHA
- archive content hash、file count、size
- `deployment_id`（公開しない場合は`null`）

Sitesの配信URLはproduction URLなので、公開しない検証ではdeploy操作を呼ばない。今回の実績はversion 3（静的）とversion 4（Worker）である。version 3のsource commitは`1e6abadb36d81516785c77793123f479a16aba64`、version 4は`67cd1745bff7b437c8199f7d785dc2e0ceb65d7c`。version 4のarchive hashは`sha256:8eec5e54c26a60c9c2f2b2f1e51335d6991a787e601c9a613b0a6079b7bb84bb`である。

## 3. 本人限定のアクセスを確認する

Sites APIのaccess policyで、`access_mode=custom`、所有者のaccount user IDだけ、外部visitor 0、editor 0を確認する。これは設定値の確認であり、実HTTPの拒否確認ではない。

実際の拒否を確認できるのは配信URLがある場合だけである。未ログイン、権限のない別アカウントについて、画面・API・ファイルの各経路を実測し、ログイン誘導または401/403を記録する。公開URLがない状態でアクセス拒否を完了扱いにしない。

## 4. 保存APIとハッシュを確認する

Site runtimeではブラウザlocalStorageを正本にしない。`oai-authenticated-user-id`を必須とし、D1に所有者・run ID・SHA-256・R2 object key・バイト数を保存し、R2にアップロードしたUTF-8原文を保存する。

- `POST /api/runs`は認証なしを401、同じowner/runで別SHAを409、サイズ超過を413にする。
- `GET /api/runs/:run_id`は所有者以外を404とし、R2から読んだ原文を再ハッシュしてD1のSHA・バイト数と一致しなければ500にする。
- JSONを`JSON.stringify`してから比較せず、入力時と読出し時の原バイト列を比較する。
- コードを更新しても、同じowner/runのデータを読み出せることを別のWorkerインスタンスで確認する。

ローカルの`apps/site/tests/storage.test.mjs`はモックD1/R2でこの境界を検査する。一時DB・合成fixtureだけを使い、本番データへ接続しない。

## 5. 記録と停止条件

[`compatibility-report.md`](compatibility-report.md)へsource SHA、package hash、Site version、archive hash、audience、fixture入力SHA、再訪前後のSHA、コード更新前後の結果を記録する。

公開範囲が想定より広い、認証ヘッダーが欠落する、入力データが欠落する、R2/D1のSHAが一致しない、またはSiteが外部取得を始める場合は、deployや再試行をせず停止する。

このrunbookは公開操作を自動化しない。公開、共有範囲変更、実データ投入、LaunchAgent登録は別の本人操作とする。
