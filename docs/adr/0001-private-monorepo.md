# 構成判断：Privateモノレポ、実行・データは分離

作成日: 2026-09-30。状態: 提案/作業計画。リポジトリ作成、コード移行、Sites公開、実取得を実施した記録ではない。

実装開始時のGitHub API確認では `beniyasan/gi-racesim` はPublicだった。
このADRのPrivate推奨は未適用であり、機密データをcommitしない運用を継続する。

## 推奨

リポジトリ名案は `gi-racesim`、Private。一人の所有者で、SiteとMac処理が共通の表示用データ形式を頻繁に変える段階なので、一つの変更で双方の契約とテストを更新できる構成を選ぶ。
「一つのリポジトリ」から「一つの実行環境」「一括デプロイ」「全データをGit保存」は導かない。

## 不変の前提

- 目的は国内平地GIのラップ・馬群・間隔・内外関係とその推移の予測。勝率・回収率中心へ戻さない。
- 収集/更新はMacBook。VAN/JV-Linkや既存競馬DBは前提にしない。
- 本収集も単一台帳・並列1・応答後120秒以上・5要求後3600秒休止・JST8〜22時・暦日/直近24時間各60要求以下。
- 未使用枠の繰越、スリープ分の取り戻し、別PC/クラウド/AIからの独立取得をしない。
- 閲覧は本人限定ChatGPT Sites。直接Cloudflare構築に戻さない。
- 初期連携は表示用JSONの本人による手動取込。Siteを開いても取得元へ通信しない。
- 合成データ、学習された予測、実測、補間、不明を分ける。

## 配置案

```text
gi-racesim/
  AGENTS.md
  CLAUDE.md
  README.md
  apps/
    site/                      # Sitesのソース。JS依存はここ
  packages/
    engine/                    # Python依存はここ
      src/gi_racesim/
        collector/
        normalization/
        datasets/
        models/
        simulation/
        evaluation/
        exporter/
      tests/
  contracts/
    viewer/v1/                 # Schema・説明・合成fixture
  ops/
    macos/                     # launchdテンプレート・更新/停止手順
  docs/
    adr/
    works/
    handoffs/
    sites/
    runbooks/
    research/
  .github/
    workflows/
    ISSUE_TEMPLATE/
```

Mac実データは `~/Library/Application Support/GIRaceSim/` に置く。state/raw/normalized/datasets/models/runs/exports/logsを分ける。開発リポジトリ・worktreeと本番台帳を混ぜない。
原HTML、SQLite、Parquet、実学習重み、実予測bundle、秘密をGitにcommitしない。テストには合成fixtureを使う。Privateでも接続した開発エージェントにはリポジトリのコードを読ませることになるため、フォルダ分割を権限境界とみなさない。

## 境界

- Site → Pythonを実行しない。Site → スクレイピングを要求しない。
- Mac → contracts準拠の結果bundleをexport。初期は人がSiteへupload。
- 共有するのはデータ形式と合成テスト例。実行時にリポジトリをデータAPIとして使わない。
- Siteの記録メタデータにD1、ファイルにR2を利用する候補はWORK-002で実機確認する。[S01]

## Sitesのソースと公開

公式案内では互換ローカルプロジェクトからの作成、バージョン保存とデプロイの分離、ローカルソース版とGitコミットの対応が説明されている。管理操作はChatGPT web/desktopが中心であり、Codex CLIの編集機能をSites公開CLIと混同しない。[S01]

apps/siteだけをプロジェクトとして扱えるかは未実機検証。WORK-002で確認し、必要なら許可リストから作るSite専用配布物を使う。これを別リポジトリの正本にしない。元ソースSHA、配布物hash、Site保存版を記録する。

初期はGitHub pushで自動デプロイしない。mainの確定commitから保存版を作り、本人が確認してデプロイする。Site上で編集した変更もGitへ戻してから次版を作り、二つの正本を育てない。全Sources/outputsの公開範囲も確認する。

本人限定は「Privateリポジトリ」と別の設定。Site・API・ファイル経路を未ログイン/権限なしアカウントで検査する。公式案内の所有者/ワークスペース管理者の範囲を確認し、組織ワークスペースを本人のみと偽らない。[S02]

## Git運用

- WORKごとにIssueと短命branchを作り、原則一つの成果物を一つのPRとしてレビューする。大きい場合は着手前に細分化。
- mainは統合先。`site`/`collector`を永久に別ブランチとして分岐させない。
- 同時作業には別worktree/別ブランチ。Git worktreeは同じリポジトリで複数ブランチを別フォルダに展開する機能。[S03]
- worktreeは安全サンドボックスではない。実台帳や秘密の権限はOS/実行環境で分ける。
- Claude Codeレビューを独立に行い、本人がmergeと公開/初回実取得の承認を行う。AIによるレビューはGitHubの別ユーザー承認と同一ではない。
- Privateのbranch protectionはGitHubプランに依存するため確認する。使えないからPublicにしない。[S04]

## CIと運用の分離

CIはモック/合成fixtureのPythonテスト、Siteビルド、契約互換性と機密混入検査だけ。依存インストール通信と競馬サイト取得は区別し、テストでは後者を禁止する。本人Macを収集用self-hosted runnerとして登録しない。
初期は軽い検査を全PRで走らせる。将来path filterを入れる場合、skipしたrequired checkがPendingとなる挙動を考慮し、必須集約checkを常に終了させる。[S05]

## 更新は三種類

1. ソース更新: PR → main。ここで取得・公開は始まらない。
2. Mac実行版更新: 収集停止 → active要求確認 → 整合バックアップ → 承認済み版へ切替 → 再開。台帳は巻き戻さない。
3. Site更新: 保存版の確認→デプロイ。結果データ更新はこれとは別のJSON取込であり、サイト再デプロイ不要の設計にする。

## 二つのリポジトリへ分ける条件

Siteコードだけ外部公開したい、参加者へ収集コードの閲覧権限を渡せない、チームやリリースが独立したときには再評価する。単にMacとSitesという実行先が違うことは、今分離する理由にしない。

## 資料

- [S01] OpenAI Sites（現在の案内）: https://learn.chatgpt.com/docs/sites
- [S02] Creating and using ChatGPT Sites: https://help.openai.com/en/articles/20001339-creating-and-using-chatgpt-sites
- [S03] Git worktree: https://git-scm.com/docs/git-worktree
- [S04] GitHub protected branches: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- [S05] GitHub workflow syntax: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- [S06] OpenAI AGENTS.md: https://learn.chatgpt.com/docs/agent-configuration/agents-md
- [S07] Claude Code memory / AGENTS.md: https://code.claude.com/docs/en/memory
