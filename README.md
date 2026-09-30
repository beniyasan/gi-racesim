# GIRaceSim

国内平地GⅠのラップと全頭の隊列推移を研究するための、オフライン優先のモノレポです。馬券・回収率・勝率の最適化を目的にしません。

## 現在の実装範囲

- `packages/engine`: SQLiteで取得枠を永続管理するゲート、保存済みデータの正規化、発走前入力と教師の分離、viewer契約の検証。
- `contracts/viewer/v1`: Mac側のexportとSite側の取り込みで共有するJSON形式と合成fixture。
- `apps/site`: 外部通信なしでfixtureまたは選択したJSONを検証・表示する最小ビューア。
- `ops/macos`: Macでの実行版切り替えとLaunchAgent登録を行う前の手順書置き場。

実サイトのHTTPアダプター、HTMLの完全対応、モデル学習、実レースの精度検証、Sitesへのデプロイは未実装です。GitHub Actionsにも実サイト通信・本番データ・認証情報を渡しません。

## ローカル検査

```bash
PYTHONPATH=packages/engine/src python -m unittest discover -s packages/engine/tests -v
cd apps/site && npm test
```

ブラウザで `apps/site/index.html` を開く場合は、fixtureの読み込みにローカルHTTPサーバーを使います。

```bash
python3 -m http.server 8000 --directory apps/site
```

## データ境界

原HTML、SQLite台帳、学習用データ、モデル重み、予測結果、認証情報はGitへ入れません。Macの本番領域は `~/Library/Application Support/GIRaceSim/` とし、コードのworktreeとは分けます。

現在のGitHubリポジトリの公開範囲は初期実装時点で確認し、機密情報をcommitしない運用を前提にしています。公開範囲の変更はGitHub側で別途確認してください。

## WORK

作業の正本は [`docs/WORKS.md`](docs/WORKS.md) と [`docs/works/`](docs/works/) です。初回実装はWORK-000の監査記録とWORK-001のモノレポ土台を中心に、後続のWORK-003〜005で使う契約・合成ビューアまで進めています。
