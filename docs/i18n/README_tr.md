<p align="center">
  <img src="../../logo.png" alt="Orbit" width="500" />
</p>

<p align="center">
  <strong>Python-yerel coklu ajan orkestrasyon cercevesi</strong>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README_zh-CN.md">简体中文</a> · <a href="README_zh-TW.md">繁體中文</a> · <a href="README_ja.md">日本語</a> · <a href="README_ko.md">한국어</a> · <a href="README_de.md">Deutsch</a> · <a href="README_fr.md">Français</a> · <a href="README_es.md">Español</a> · <a href="README_it.md">Italiano</a> · <a href="README_pt.md">Português</a> · <a href="README_ru.md">Русский</a> · <a href="README_tr.md">Türkçe</a> · <a href="README_vi.md">Tiếng Việt</a>
</p>

---

## Orbit Nedir?

Orbit, Python-yerel bir coklu ajan orkestrasyon cercevesidir. 30'dan fazla uzman ajan rolu, 35'ten fazla yeniden kullanilabilir beceri ve takim koordinasyonu icin bir calisma zamani motoru ile yapay zeka ajan is akislarini olusturmak, koordine etmek ve yonetmek icin eksiksiz bir arac seti sunar.

## Ozellikler

- **30 Ajan Rolu** — Her gorev icin uzman ajanlar: `$architect`, `$executor`, `$debugger`, `$code-reviewer`, `$planner` ve dahasi
- **35+ Beceri** — Yeniden kullanilabilir is akisi becerileri: `$plan`, `$team`, `$autopilot`, `$ralph`, `$deep-interview`, `$doctor`
- **Calisma Zamani Motoru** — Yetki yonetimi, dagitim ve posta kutusu koordinasyonu ile olay kaynakli calisma zamani
- **Takim Orkestrasyonu** — tmux tabanli coklu ajan koordinasyonu ve rol tabanli yonlendirme
- **Sparkshell** — Yapay zeka destekli komut yurutme ve cikti ozeti
- **Explorer** — Izin verilen komutlarla guvenli kod tabani kesfetme
- **HUD** — Gercek zamanli ajan durum paneli
- **Pipeline** — Yapilandrilabilir cok asamali yurutme hatti
- **Autoresearch** — Degerlendirme sozlesmeleri ile otomatik arastirma gorevleri

## Hizli Baslangic

```bash
pip install orbit
orbit summary
orbit doctor
orbit agents
orbit skills
orbit ask "review security" --role architect
orbit setup
```

## Ajanlar

| Kategori | Ajanlar |
|----------|---------|
| **Build** | explore, analyst, planner, architect, debugger, executor, team-executor, verifier |
| **Review** | style-reviewer, quality-reviewer, api-reviewer, security-reviewer, performance-reviewer, code-reviewer |
| **Domain** | dependency-expert, test-engineer, quality-strategist, build-fixer, designer, writer, qa-tester, git-master, code-simplifier, researcher |
| **Urun** | product-manager, ux-researcher, information-architect, product-analyst |
| **Koordinasyon** | critic, vision |

## Lisans

MIT
