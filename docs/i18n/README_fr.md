<p align="center">
  <img src="../../logo.png" alt="Orbit" width="500" />
</p>

<p align="center">
  <strong>Framework d'orchestration multi-agents natif Python</strong>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README_zh-CN.md">简体中文</a> · <a href="README_zh-TW.md">繁體中文</a> · <a href="README_ja.md">日本語</a> · <a href="README_ko.md">한국어</a> · <a href="README_de.md">Deutsch</a> · <a href="README_fr.md">Français</a> · <a href="README_es.md">Español</a> · <a href="README_it.md">Italiano</a> · <a href="README_pt.md">Português</a> · <a href="README_ru.md">Русский</a> · <a href="README_tr.md">Türkçe</a> · <a href="README_vi.md">Tiếng Việt</a>
</p>

---

## Qu'est-ce qu'Orbit ?

Orbit est un framework d'orchestration multi-agents natif Python. Il fournit une boite a outils complete pour construire, coordonner et gerer des workflows d'agents IA avec 30+ roles d'agents specialises, 35+ competences reutilisables et un moteur d'execution pour la coordination d'equipe.

## Fonctionnalites

- **30 roles d'agents** — Des agents specialises pour chaque tache : `$architect`, `$executor`, `$debugger`, `$code-reviewer`, `$planner` etc.
- **35+ competences** — Competences de workflow reutilisables : `$plan`, `$team`, `$autopilot`, `$ralph`, `$deep-interview`, `$doctor`
- **Moteur d'execution** — Runtime event-source avec gestion des autorisations, dispatch et coordination par boite aux lettres
- **Orchestration d'equipe** — Coordination multi-agents basee sur tmux avec routage par role
- **Sparkshell** — Execution de commandes avec resume de sortie par IA
- **Explorer** — Exploration securisee du codebase avec commandes autorisees
- **HUD** — Tableau de bord en temps reel de l'etat des agents
- **Pipeline** — Pipeline d'execution multi-etapes configurable
- **Autoresearch** — Missions de recherche automatisees avec contrats d'evaluation

## Demarrage rapide

```bash
pip install orbit
orbit summary
orbit doctor
orbit agents
orbit skills
orbit ask "review security" --role architect
orbit setup
```

## Agents

| Categorie | Agents |
|-----------|--------|
| **Build** | explore, analyst, planner, architect, debugger, executor, team-executor, verifier |
| **Review** | style-reviewer, quality-reviewer, api-reviewer, security-reviewer, performance-reviewer, code-reviewer |
| **Domaine** | dependency-expert, test-engineer, quality-strategist, build-fixer, designer, writer, qa-tester, git-master, code-simplifier, researcher |
| **Produit** | product-manager, ux-researcher, information-architect, product-analyst |
| **Coordination** | critic, vision |

## Licence

MIT
