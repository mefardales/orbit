<p align="center">
  <img src="../../logo.png" alt="Orbit" width="500" />
</p>

<p align="center">
  <strong>Python 네이티브 멀티 에이전트 오케스트레이션 프레임워크</strong>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README_zh-CN.md">简体中文</a> · <a href="README_zh-TW.md">繁體中文</a> · <a href="README_ja.md">日本語</a> · <a href="README_ko.md">한국어</a> · <a href="README_de.md">Deutsch</a> · <a href="README_fr.md">Français</a> · <a href="README_es.md">Español</a> · <a href="README_it.md">Italiano</a> · <a href="README_pt.md">Português</a> · <a href="README_ru.md">Русский</a> · <a href="README_tr.md">Türkçe</a> · <a href="README_vi.md">Tiếng Việt</a>
</p>

---

## Orbit란?

Orbit는 Python 네이티브 멀티 에이전트 오케스트레이션 프레임워크입니다. 30개 이상의 전문 에이전트 역할, 35개 이상의 재사용 가능한 스킬, 팀 조율을 위한 런타임 엔진을 갖춘 AI 에이전트 워크플로 구축, 조율, 관리를 위한 완전한 도구 모음을 제공합니다.

## 기능

- **30개 에이전트 역할** — 모든 작업을 위한 전문 에이전트: `$architect`, `$executor`, `$debugger`, `$code-reviewer`, `$planner` 등
- **35개 이상의 스킬** — 재사용 가능한 워크플로 스킬: `$plan`, `$team`, `$autopilot`, `$ralph`, `$deep-interview`, `$doctor`
- **런타임 엔진** — 권한 관리, 디스패치, 메일박스 조율을 갖춘 이벤트 소싱 런타임
- **팀 오케스트레이션** — tmux 기반 멀티 에이전트 조율 및 역할 기반 라우팅
- **Sparkshell** — AI 기반 명령 실행 및 출력 요약
- **Explorer** — 허용 목록 명령어를 통한 안전한 코드베이스 탐색
- **HUD** — 실시간 에이전트 상태 표시
- **Pipeline** — 구성 가능한 다단계 실행 파이프라인
- **Autoresearch** — 평가 계약을 포함한 자동화 연구 미션

## 빠른 시작

```bash
pip install orbit
orbit summary
orbit doctor
orbit agents
orbit skills
orbit ask "review security" --role architect
orbit setup
```

## 에이전트

| 카테고리 | 에이전트 |
|---------|---------|
| **빌드** | explore, analyst, planner, architect, debugger, executor, team-executor, verifier |
| **리뷰** | style-reviewer, quality-reviewer, api-reviewer, security-reviewer, performance-reviewer, code-reviewer |
| **도메인** | dependency-expert, test-engineer, quality-strategist, build-fixer, designer, writer, qa-tester, git-master, code-simplifier, researcher |
| **프로덕트** | product-manager, ux-researcher, information-architect, product-analyst |
| **코디네이션** | critic, vision |

## 라이선스

MIT
