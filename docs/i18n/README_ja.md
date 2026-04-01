<p align="center">
  <img src="../../logo.png" alt="Orbit" width="500" />
</p>

<p align="center">
  <strong>Pythonネイティブ マルチエージェント オーケストレーション フレームワーク</strong>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README_zh-CN.md">简体中文</a> · <a href="README_zh-TW.md">繁體中文</a> · <a href="README_ja.md">日本語</a> · <a href="README_ko.md">한국어</a> · <a href="README_de.md">Deutsch</a> · <a href="README_fr.md">Français</a> · <a href="README_es.md">Español</a> · <a href="README_it.md">Italiano</a> · <a href="README_pt.md">Português</a> · <a href="README_ru.md">Русский</a> · <a href="README_tr.md">Türkçe</a> · <a href="README_vi.md">Tiếng Việt</a>
</p>

---

## Orbit とは？

Orbit は Python ネイティブのマルチエージェント オーケストレーション フレームワークです。30以上の専門エージェントロール、35以上の再利用可能なスキル、チーム連携のためのランタイムエンジンを備えた、AIエージェントワークフローの構築・調整・管理のための完全なツールキットを提供します。

## 機能

- **30のエージェントロール** — あらゆるタスクに特化したエージェント：`$architect`、`$executor`、`$debugger`、`$code-reviewer`、`$planner` など
- **35以上のスキル** — 再利用可能なワークフロースキル：`$plan`、`$team`、`$autopilot`、`$ralph`、`$deep-interview`、`$doctor`
- **ランタイムエンジン** — 権限管理、ディスパッチ、メールボックス連携を備えたイベントソースランタイム
- **チームオーケストレーション** — tmuxベースのマルチエージェント連携とロールベースルーティング
- **Sparkshell** — AI搭載のコマンド実行と出力要約
- **Explorer** — ホワイトリストコマンドによる安全なコードベース探索
- **HUD** — リアルタイムエージェントステータス表示
- **Pipeline** — 設定可能なマルチステージ実行パイプライン
- **Autoresearch** — 評価コントラクト付き自動リサーチミッション

## クイックスタート

```bash
pip install orbit
orbit summary
orbit doctor
orbit agents
orbit skills
orbit ask "review security" --role architect
orbit setup
```

## エージェント

| カテゴリ | エージェント |
|---------|------------|
| **ビルド** | explore, analyst, planner, architect, debugger, executor, team-executor, verifier |
| **レビュー** | style-reviewer, quality-reviewer, api-reviewer, security-reviewer, performance-reviewer, code-reviewer |
| **ドメイン** | dependency-expert, test-engineer, quality-strategist, build-fixer, designer, writer, qa-tester, git-master, code-simplifier, researcher |
| **プロダクト** | product-manager, ux-researcher, information-architect, product-analyst |
| **コーディネーション** | critic, vision |

## ライセンス

MIT
