<p align="center">
  <img src="../../logo.png" alt="Orbit" width="500" />
</p>

<p align="center">
  <strong>Framework de orquestracao multi-agente nativo em Python</strong>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README_zh-CN.md">简体中文</a> · <a href="README_zh-TW.md">繁體中文</a> · <a href="README_ja.md">日本語</a> · <a href="README_ko.md">한국어</a> · <a href="README_de.md">Deutsch</a> · <a href="README_fr.md">Français</a> · <a href="README_es.md">Español</a> · <a href="README_it.md">Italiano</a> · <a href="README_pt.md">Português</a> · <a href="README_ru.md">Русский</a> · <a href="README_tr.md">Türkçe</a> · <a href="README_vi.md">Tiếng Việt</a>
</p>

---

## O que e o Orbit?

Orbit e um framework de orquestracao multi-agente nativo em Python. Ele fornece um kit de ferramentas completo para construir, coordenar e gerenciar workflows de agentes IA com 30+ papeis de agentes especializados, 35+ habilidades reutilizaveis e um motor de execucao para coordenacao de equipes.

## Funcionalidades

- **30 papeis de agentes** — Agentes especializados para cada tarefa: `$architect`, `$executor`, `$debugger`, `$code-reviewer`, `$planner` e mais
- **35+ habilidades** — Habilidades de workflow reutilizaveis: `$plan`, `$team`, `$autopilot`, `$ralph`, `$deep-interview`, `$doctor`
- **Motor de execucao** — Runtime baseado em event-sourcing com gestao de permissoes, despacho e coordenacao por caixa de correio
- **Orquestracao de equipes** — Coordenacao multi-agente baseada em tmux com roteamento por papeis
- **Sparkshell** — Execucao de comandos com resumo de saida alimentado por IA
- **Explorer** — Exploracao segura do codigo com comandos permitidos
- **HUD** — Painel de status dos agentes em tempo real
- **Pipeline** — Pipeline de execucao multi-estagio configuravel
- **Autoresearch** — Missoes de pesquisa automatizadas com contratos de avaliacao

## Inicio rapido

```bash
pip install orbit
orbit summary
orbit doctor
orbit agents
orbit skills
orbit ask "review security" --role architect
orbit setup
```

## Agentes

| Categoria | Agentes |
|-----------|---------|
| **Build** | explore, analyst, planner, architect, debugger, executor, team-executor, verifier |
| **Review** | style-reviewer, quality-reviewer, api-reviewer, security-reviewer, performance-reviewer, code-reviewer |
| **Dominio** | dependency-expert, test-engineer, quality-strategist, build-fixer, designer, writer, qa-tester, git-master, code-simplifier, researcher |
| **Produto** | product-manager, ux-researcher, information-architect, product-analyst |
| **Coordenacao** | critic, vision |

## Licenca

MIT
