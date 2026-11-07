# App Development Git SSOT Rule

このrepoで開発するCodex / Claude Codeは毎回このRuleを適用し、利用可能なら
`app-development-git-ssot` Skillを読み込む。アプリ・ソフトウェア開発、Git実装、
commit、push、branch作成、release、milestone、repo初期化、中断・再開、handoffが対象。

- GitHub = 残す価値のあるcommit済み開発履歴のSSOT。
- Local = 次のcommitを作る開発環境。未commitの試行錯誤をGitHubへ同期する必要はない。
- main = 検証済みの安定状態。app build/test・必要なUI/実機確認を満たした状態だけを入れる。
- feature / impl等 = 途中でも復元価値のある意味のあるcheckpointをcommit / push可能。
  checkpointの未検証・既知の不具合は明示し、mainと同じ安定状態とは主張しない。
- commit / push / remote設定 / 公開 / history rewriteはユーザー・projectの既存許可に従う。

## Gitへ残すもの

Production source、Test、Production asset、必要なconfiguration、恒久的な設計資料、
README、復元に必要なscript、commit history。
画像・動画という拡張子だけで禁止しない。採用されたProduction asset・正式仕様は保持する。

Simulator screenshot、Visual Evidence、比較画像、検証用GIF/動画、diagnostic log、
xcresult、DerivedData、build生成物、cache、一時script output、作業用copyは原則Local-only。
Evidenceは目視・判断完了で役割を終える。Evidence自体でなく採用した実装・Test・判断を残す。
正式採用された資料は用途を明示し、恒久資料のpathへ配置する。既存ファイルの削除は勝手に行わない。
`docs/verification/`、`evidence/`、`Evidence/`、`DerivedData/`、`build/`、`.build/`、
`*.xcresult` は機械的拒否対象。他のpathにあるEvidenceもagentが用途を判断して除外する。

## Secrets

API Key、token、password、signing credential、certificate、private key、provisioning profile、
.env実値その他secretはcommit禁止。Local / Keychain / Environmentに保持しbuild/runtimeで注入する。
example/templateはplaceholderのみGit可。実値を含むexampleも禁止。
`.env` / `.env.*` / `*.env`（example/template/sample suffix除く）、
`*.p12`、`*.pfx`、`*.mobileprovision`、`*.p8`、`*.pem`、`*.key`、`*.cer`、`*.crt`を拒否する。
content scannerは代表的token/private keyとsecret assignmentを検出する補助であり、全secretの不在を証明しない。
secret検出は値を出力せずpathとruleのみ出力する。例外でsecretを許可しない。

## 初回導入と既存履歴

導入時は現在のindexと全reachable historyを先に監査する。既存Evidence / secretを
legacy例外で許可しない。違反があればenforcementを有効化する前に監査結果を報告し、
必要な初回cleanupの明示許可を得る。cleanupではrepository外の全履歴bundleと未commit変更の
退避・復元確認を先に行い、用途で決めた明示pathだけを対象にする。
Production source / asset / Test / 有効な履歴のequivalence確認後にpolicyを有効化する。
history rewriteとremote更新は自動実行しない。許可されたrewriteのremote更新でも
期待するremote SHAを確認し、明示lease付きforce-with-leaseだけを使う。

## 作業開始・commit / push前

1. repo instructions、`git branch --show-current`、`git rev-parse HEAD`、`git status --short`を確認。
2. staged diffを確認。Production / Test / configとEvidence / secretを用途で区別する。
3. 変更に必要なverificationを実行し結果を読む。検証済み・完了の主張前は
   `verification-before-completion` Skillを適用。UI/実機未確認は明記する。
4. `python3 .repo-policy/check.py --index`、`git diff --cached --check` を実行。
5. push前は `python3 .repo-policy/check.py --history HEAD`（実際にはpush対象ref）を実行。
   hookはstdinの全push対象refを同じscannerで確認。既存history違反も拒否する。
6. `git config --get core.hooksPath` が `.githooks` であることを確認。
   clone/別worktree/再開で未設定なら共通Skillのbootstrapを再実行する。
7. handoffにはbranch/HEAD、dirty状態、verification結果、未完了、Next Owner/Actionを残す。

## Enforcementの範囲

pre-commitはindex全体（staged bytes）を確認し、unstaged clean copyでsecretを隠せない。
pre-pushとGitHub Actionsはpush対象の全到達可能commit treeを確認し、途中commitの違反も検出する。
ignoreだけでは既存tracked/historyは除外されない。違反は削除やrewriteせず、まず監査して判断を求める。
hook回避・policy改変はローカルで可能。CIは送信後の検出であり送信阻止ではない。
GitHub公開後、mainでPR必須・app build/testおよび `app-git-ssot` 必須status check・
force push禁止・bypass制限を設定してmainの安定状態を保護する。
repoの検証結果そのものはCIログ・簡潔な判断として残し、一時Evidenceをcommitしない。
