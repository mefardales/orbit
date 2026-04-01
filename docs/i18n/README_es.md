<p align="center">
  <img src="../../logo.png" alt="Orbit" width="500" />
</p>

<p align="center">
  <strong>Framework de orquestacion multi-agente nativo en Python</strong>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README_zh-CN.md">简体中文</a> · <a href="README_zh-TW.md">繁體中文</a> · <a href="README_ja.md">日本語</a> · <a href="README_ko.md">한국어</a> · <a href="README_de.md">Deutsch</a> · <a href="README_fr.md">Français</a> · <a href="README_es.md">Español</a> · <a href="README_it.md">Italiano</a> · <a href="README_pt.md">Português</a> · <a href="README_ru.md">Русский</a> · <a href="README_tr.md">Türkçe</a> · <a href="README_vi.md">Tiếng Việt</a>
</p>

---

## Que es Orbit?

Orbit es un framework de orquestacion multi-agente nativo en Python. Proporciona un kit de herramientas completo para construir, coordinar y gestionar flujos de trabajo de agentes IA con 30+ roles de agentes especializados, 35+ habilidades reutilizables y un motor de ejecucion para coordinacion de equipos.

## Caracteristicas

- **30 roles de agentes** — Agentes especializados para cada tarea: `$architect`, `$executor`, `$debugger`, `$code-reviewer`, `$planner` y mas
- **35+ habilidades** — Habilidades de flujo de trabajo reutilizables: `$plan`, `$team`, `$autopilot`, `$ralph`, `$deep-interview`, `$doctor`
- **Motor de ejecucion** — Runtime basado en event-sourcing con gestion de permisos, despacho y coordinacion por buzon
- **Orquestacion de equipos** — Coordinacion multi-agente basada en tmux con enrutamiento por roles
- **Sparkshell** — Ejecucion de comandos con resumen de salida potenciado por IA
- **Explorer** — Exploracion segura del codigo con comandos permitidos
- **HUD** — Panel de estado de agentes en tiempo real
- **Pipeline** — Pipeline de ejecucion multi-etapa configurable
- **Autoresearch** — Misiones de investigacion automatizadas con contratos de evaluacion

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
| **Producto** | product-manager, ux-researcher, information-architect, product-analyst |
| **Coordinacion** | critic, vision |

## Licencia

MIT
