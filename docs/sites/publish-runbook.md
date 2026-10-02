# Sites公開経路の検査手順（WORK-002）

この手順は、`apps/site`を本人限定のChatGPT Siteへ持ち込む経路を記録する
ためのものです。Siteの作成・保存・公開はGitHub pushから自動では始まりません。
実行結果は [`compatibility-report.md`](compatibility-report.md) に追記します。

## 1. Gitと配布物を固定する

mainのレビュー済みコミットを起点に、リポジトリ直下で次を実行します。

```bash
git status --short
git rev-parse HEAD
python3 scripts/site/package.py --output /private/tmp/gi-racesim-site-package
cat /private/tmp/gi-racesim-site-package/GIRACESIM_SITE_MANIFEST.json
```

出力先が存在して中身がある場合、スクリプトは上書きせず停止します。manifestには
ソースSHA、許可したファイルのサイズとSHA-256、配布物のSHA-256が入ります。
`apps/site`以外のファイル、原HTML、SQLite、モデル、認証情報は配布物に含めません。
配布物を作り直した場合は、Siteへ渡した版とmanifestを対応付けて残します。

## 2. Sitesで作成・プレビューする

現在の公式操作はChatGPT webのWork、またはデスクトップアプリのWork/Codexから
Site作成を開始し、プロンプトに「website」または`@Sites`を含める流れです。
配布物を入力できるか、`apps/site`をローカルソースとして扱えるかはアカウントと
表示されたUIで確認します。UIにその経路がない場合は、未確認のCLI/APIを作らず、
その時点で停止してreportに記録します。

プレビューでは、合成fixtureを表示し、次を確認します。

- レース名、入力時点、データ版、由来が表示される
- ラップ分布と代表試行の地点別隊列が表示される
- `quality`の観測不足と合成データの注記が残る
- JSONの文字列がHTMLとして実行されない
- Siteを開くだけで競馬サイトや任意URLへ通信しない

変更を保存する場合は、公開前にSiteのバージョンを保存します。デプロイURLは
production URLとして扱われるため、プレビュー確認前にPublishしません。

## 3. 本人限定のアクセスを確認する

Share設定では、最初に所有者とworkspace管理者だけの範囲を選びます。公開範囲を
`Anyone on the Internet`へ変更しません。所有者のプレビュー、未ログイン状態、権限の
ないアカウントまたはブラウザで、画面・ファイル・APIの各経路を確認します。
未検証の経路は成功と記録しません。

Site作成後に表示されたURL、Share設定、保存版、配布物manifestのSHAをreportへ記録
します。認証状態はブラウザの実際の表示（ログイン誘導、401/403等）で記録し、
リポジトリのPrivate設定だけから本人限定とは判断しません。

## 4. 保存と再訪を確認する

合成fixtureを1件だけ取り込み、Siteを閉じて再訪します。画面に同じ内容が表示され、
保存したデータのハッシュが変わらないことを記録します。D1/R2等の保存機能がUIで
提供される場合も、実際に確認できた経路・権限・失敗時の挙動だけを記録します。
未確認のバインディング名やAPIをコードに追加しません。

コードを更新した場合は、保存済みデータが残ることと、Siteのコード版と結果データの
版が別に確認できることを検査します。失敗した取込は一覧へ公開せず、既存の正常な
合成runを壊さないことを確認します。

## 5. 記録と停止条件

最低限、次を [`compatibility-report.md`](compatibility-report.md) に記録します。

| 項目 | 記録内容 |
| --- | --- |
| source | Git SHA、配布物manifestのSHA-256 |
| Site | Site名、保存版、表示されたURL |
| audience | Shareで選んだ範囲、未ログイン/権限なしの実挙動 |
| import | run_id、入力JSONのSHA、再訪後のSHA |
| code update | 更新前後のSite版とデータの保持 |
| 未実施 | 確認できなかった経路、理由、次の本人操作 |

公開範囲が想定より広い、認証要求が不明、入力データが欠落する、またはSiteが
外部取得を始める場合は、Publishや再試行をせず停止します。

2026-10-02に、合成fixture `run-synthetic-001`（入力SHA `9070dd48...`）を使った
本人限定の下書きversion 2について、保存版`index.html`のプレビュー表示、ビューアを
閉じた後の同じ下書きからの再表示を確認した。公開URLは発行していない。Sitesの
インタラクティブプレビュー基盤はサンドボックス制限で起動できなかったため、実機確認の
証拠は互換性レポートに記録した保存版HTMLの非公開sandboxプレビューである。

このrunbookは公開操作を自動化しない。公開、共有範囲変更、実データ投入、未確認の
CLI/API追加は行わない。
