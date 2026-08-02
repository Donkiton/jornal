# Маркетинговые материалы

В этой папке находятся план продвижения, промпты, исходные фоны и пять готовых рекламных изображений для версии 1.0.2.

## Состав

- [`marketing-plan.md`](./marketing-plan.md) — план продвижения на первые 90 дней;
- [`image-prompts.md`](./image-prompts.md) — промпты и единое визуальное направление;
- [`visuals/*-background.png`](./visuals) — исходные изображения без наложенного русского текста;
- [`visuals/01-hero.png`](./visuals/01-hero.png) — главный баннер;
- [`visuals/02-features.png`](./visuals/02-features.png) — карточка функций;
- [`visuals/03-data-control.png`](./visuals/03-data-control.png) — карточка хранения данных;
- [`visuals/04-workflow.png`](./visuals/04-workflow.png) — рабочий сценарий;
- [`visuals/05-pilot.png`](./visuals/05-pilot.png) — приглашение на пилот.

## Повторная сборка изображений

```powershell
python -m pip install -r marketing\requirements.txt
python marketing\render_visuals.py
```

Скрипт использует локальные шрифты Segoe UI из Windows и заново создаёт пять финальных PNG из сохранённых фонов. Текст накладывается программно, поэтому русские формулировки остаются точными.
