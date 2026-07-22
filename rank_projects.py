import json
import re
from pathlib import Path

SRC = Path("data/projects.json")
OUT = Path("data/ranking.json")

STRONG = {
    "ПД/РД/проектирование": [r"проектн\w* документац", r"рабоч\w* документац", r"\bпд\b", r"\bрд\b", r"проектирован", r"капитальн\w* ремонт", r"реконструкц"],
    "ПОС/ППР": [r"\bпос\b", r"\bппр\b", r"организац\w* строительств", r"проект производств\w* работ"],
    "ОВ/вентиляция": [r"\bов\b", r"овик", r"вентиляц", r"отоплен", r"теплоснаб", r"воздухообмен"],
    "ПБ/АПС": [r"пожар", r"\bапс\b", r"соуэ", r"пожарн\w* безопас", r"огнезащит"],
    "ПЗУ/ОДИ/МГН": [r"\bпзу\b", r"спозу", r"\bоди\b", r"\bмгн\b", r"маломобиль", r"генплан"],
    "Экспертиза/правки": [r"экспертиз", r"замечан", r"внести правк", r"корректиров", r"проверить документац", r"аудит проект"],
    "AutoCAD/DWG/чертежи": [r"autocad", r"nanocad", r"\bdwg\b", r"чертеж", r"оцифров", r"перечерт", r"компас"],
    "Сметы/ВОР": [r"смет", r"\bвор\b", r"\bлср\b", r"\bнцс\b", r"\bпир\b", r"\bсбц\b", r"объем\w* работ"],
}

MEDIUM = {
    "Excel/таблицы": [r"excel", r"google sheets", r"гугл\w* таблиц", r"таблиц", r"xlsx"],
    "Python/автоматизация": [r"python", r"автоматизац", r"скрипт", r"парс", r"обработк\w* файлов", r"api", r"xml", r"pdf", r"docx"],
    "Вектор/макеты": [r"вектор", r"\bsvg\b", r"pdf/x", r"eps", r"мастер-макет"],
    "Техническая проверка": [r"при[её]мк", r"чек-лист", r"техническ\w* провер", r"регламент", r"тз"],
}

NEGATIVE = {
    "Маркетинг/SMM/SEO": [r"\bsmm\b", r"\bseo\b", r"продвижен", r"таргет", r"директ", r"лидогенерац", r"контент-план", r"соцсет", r"социальн\w* сет"],
    "Видео/моушн": [r"монтаж", r"видео", r"after effects", r"premiere", r"моушн", r"shorts", r"youtube"],
    "Веб-разработка": [r"wordpress", r"react", r"next\.?js", r"php", r"frontend", r"backend", r"верстк", r"сайт под ключ"],
    "Продажи/обзвон": [r"обзвон", r"продаж", r"лпр", r"поиск клиентов", r"рассылк"],
}

HARD_RISK = {
    "Расчёт конструкций": [r"расчет на прочност", r"расч[её]т прочност", r"расч[её]т.*металлоконструк", r"оптимизац.*металл", r"снегов\w*.*ветров", r"\bscad\b", r"\bлира\b"],
    "Спецстек": [r"bitrix24", r"\bn8n\b", r"salebot", r"altium", r"supabase", r"silex", r"laravel", r"1с-битрикс"],
}


def matches(text, patterns):
    return any(re.search(p, text, re.I) for p in patterns)


def budget_points(price, max_budget):
    b = max_budget or price or 0
    if b >= 100000:
        return 3.0
    if b >= 50000:
        return 2.5
    if b >= 20000:
        return 2.0
    if b >= 10000:
        return 1.3
    if b >= 5000:
        return 0.6
    if b <= 1500:
        return -1.5
    if b <= 3000:
        return -0.8
    return 0.0


def score_project(p):
    text = f"{p.get('title','')} {p.get('description','')}".lower()
    score = 0.0
    tags = []
    risks = []

    for tag, pats in STRONG.items():
        if matches(text, pats):
            score += 3.0
            tags.append(tag)
    for tag, pats in MEDIUM.items():
        if matches(text, pats):
            score += 1.5
            tags.append(tag)
    for tag, pats in NEGATIVE.items():
        if matches(text, pats):
            score -= 2.5
            risks.append(tag)
    for tag, pats in HARD_RISK.items():
        if matches(text, pats):
            score -= 4.0
            risks.append(tag)

    score += budget_points(p.get("price"), p.get("max_budget"))

    offers = p.get("offers")
    if isinstance(offers, int):
        if offers == 0:
            score += 1.5
        elif offers <= 3:
            score += 1.0
        elif offers <= 8:
            score += 0.3
        elif offers >= 25:
            score -= 1.2
        elif offers >= 15:
            score -= 0.6

    hire = p.get("hire_rate")
    if isinstance(hire, (int, float)):
        if hire >= 80:
            score += 1.0
        elif hire >= 60:
            score += 0.6
        elif hire <= 10:
            score -= 0.8

    bp = p.get("buyer_projects")
    if isinstance(bp, int):
        if bp >= 20:
            score += 0.5
        elif bp >= 5:
            score += 0.2

    # Tiny freshness bonus, not enough to outweigh fit.
    page = p.get("source_page") or 99
    if page <= 3:
        score += 0.3
    elif page >= 30:
        score -= 0.2

    return round(score, 1), tags, risks


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    ranked = []
    for p in data.get("projects", []):
        score, tags, risks = score_project(p)
        row = dict(p)
        row["auto_score"] = score
        row["match_tags"] = tags
        row["risk_tags"] = risks
        ranked.append(row)

    ranked.sort(key=lambda p: (p["auto_score"], p.get("max_budget") or p.get("price") or 0, -(p.get("offers") or 0)), reverse=True)

    # Keep a broad pool for manual review; also retain total scan metadata.
    out = {
        "scraped_at": data.get("scraped_at"),
        "scanned_pages": data.get("scanned_pages"),
        "total_projects": len(ranked),
        "candidate_count": min(140, len(ranked)),
        "projects": ranked[:140],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Ranked {len(ranked)} projects; wrote top {len(out['projects'])}")


if __name__ == "__main__":
    main()
