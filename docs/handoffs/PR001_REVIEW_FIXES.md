# PR #1 レビュー・CI修正

基点: `b60dcabeb613258d5b8a04a672fa123aab2294c0`。

## 対応内容

- `freeze_manifest` はSHA-256を64文字という長さだけでなく、ASCIIの16進数と文字列型で検査する。大文字は小文字へ正規化し、入力を変更しない。非文字列・改行・非16進文字を拒否する。
- マニフェストに保持するsourceメタデータをコピーし、呼出し側の後の変更が凍結済み内容を変えないようにする。元ファイルの実バイトとハッシュの照合は、この関数だけでは行わない。
- CIの実データ検査は、正規のPythonソース `packages/engine/src/gi_racesim/datasets/*.py` を誤って拒否しない。DB・モデル・認証情報のファイルや実データ用ディレクトリは引き続き拒否する。この検査はパス検査であり、秘密の本文検出器ではない。
- ローカルHTTPサーバーの公開ルート `apps/site` に合わせ、画面のschema・fixture・faviconを `./public/` 経由で参照する。
- 共通fixtureも同期・一致検査の対象にする。
- manifestの回帰テスト10件、リポジトリのパス検査9件、Siteのアセット検査3件を追加する。

## Macでの反映

リポジトリ内で `git status --short` を確認する。変更があれば先に内容を確認し、破棄や強制上書きはしない。

クリーンなPRブランチの場合:

```bash
git switch work/001-offline-foundation
git pull --ff-only origin work/001-offline-foundation
```

今回の修正はPRへ直接反映するため、前回の `pr1-mac-fixes.patch` を重ねて適用しない。前回ZIPの未適用分まで全て取り込んだという意味ではなく、このPRには `scripts/doctor.py` や `scripts/check_local.py` は含まれない。旧ZIPを既に適用した作業フォルダーは、差分を確認してから統合する。

Python環境とNodeを確認したうえで、リポジトリ直下から次を実行する:

```bash
PYTHONPATH=packages/engine/src python3 -m unittest discover -s packages/engine/tests -v
python3 -m unittest discover -s scripts/tests -v
python3 scripts/check_tracked_files.py
(cd apps/site && npm test)
python3 -m http.server 8000 --bind 127.0.0.1 --directory apps/site
```

最後のサーバーを起動したら、Macのブラウザで `http://127.0.0.1:8000/` を開き、合成fixtureの表示を確認する。

## 境界

この修正は収集間隔・取得台帳・モデルの目的を変更しない。実サイト取得、LaunchAgent登録、Sitesの公開、リポジトリの公開範囲変更、mainへのmergeは別操作。Mac実機の検査やモデル精度の検証を行ったことにはしない。CI結果は修正コミットに対応する最新runを確認する。
