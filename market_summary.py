import json
import re
import statistics
from collections import Counter
from pathlib import Path

SRC = Path("data/projects.json")
OUT = Path("data/market_summary.json")

# Market slices that are realistically adjacent to the owner's current skills.
CATEGORIES = {
    "AutoCAD/DWG/чертежи": [
        r"autocad", r"nano\s*cad", r"nanocad", r"\bdwg\b", r"\bdxf\b",
        r"черт[её]ж", r"перечерт", r"оцифров.*черт", r"компас[- ]?3d",
    ],
    "Проектная документация/ПД/РД": [
        r"проектн\w* документац", r"рабоч\w* документац", r"\bпд\b", r"\bрд\b",
        r"стади[яи]\s*п\b", r"постановлен.*87", r"пп\s*87", r"проектирован",
    ],
    "Инженерные сети ОВ/ВК/ЭОМ": [
        r"\bов\b", r"овик", r"вентиляц", r"отоплен", r"теплоснаб",
        r"\bвк\b", r"водоснаб", r"канализац", r"\bэом\b", r"электроснаб",
        r"электрик\w* проект", r"инженерн\w* сет",
    ],
    "Сметы/ВОР/объёмы": [
        r"смет", r"\bвор\b", r"\bлср\b", r"ведомост\w* объ[её]м", r"объ[её]м\w* работ",
        r"подсч[её]т\w* объ[её]м", r"расценк", r"гранд[- ]?смет",
    ],
    "Экспертиза/правки проекта": [
        r"экспертиз", r"замечан\w* эксперт", r"ответ\w* на замечан",
        r"корректиров\w* проект", r"внести правк\w*.*проект", r"аудит\w* проект",
    ],
    "ПЗУ/генплан/СПОЗУ": [
        r"\bпзу\b", r"спозу", r"генплан", r"генеральн\w* план", r"посадк\w* здан",
        r"схем\w* планировочн\w* организац",
    ],
    "ПОС/ППР": [
        r"\bпос\b", r"\bппр\b", r"организац\w* строительств", r"проект производств\w* работ",
        r"стройгенплан",
    ],
    "Excel/таблицы/расчёты": [
        r"\bexcel\b", r"xlsx", r"google sheets", r"гугл\w* таблиц", r"электронн\w* таблиц",
        r"формул\w* excel", r"сводн\w* таблиц", r"макрос\w* excel",
    ],
    "Python/скрипты/автоматизация": [
        r"\bpython\b", r"python[- ]?скрипт", r"автоматизац\w*", r"скрипт\w*",
        r"парсер", r"парсинг", r"обработк\w* файлов", r"генерац\w* документ",
        r"автоматическ\w* формирован",
    ],
    "Коммерческие предложения/Word/PDF": [
        r"коммерческ\w* предложен", r"\bткп\b", r"шаблон\w* кп\b", r"\bword\b", r"\bdocx\b",
        r"шаблон\w* документ", r"оформ\w* документ", r"формирован\w* pdf", r"заполн\w* pdf",
    ],
    "Техническая документация/ТЗ": [
        r"техническ\w* задан", r"\bтз\b", r"техническ\w* документац", r"паспорт\w* оборуд",
        r"техническ\w* описан", r"инструкц\w*", r"регламент\w*", r"спецификац\w*",
    ],
    "Вектор/макеты/Inkscape": [
        r"вектор", r"\bsvg\b", r"\beps\b", r"coreldraw", r"illustrator", r"inkscape",
        r"макет\w* печат", r"подготов\w* к печат",
    ],
    "Презентации/PowerPoint": [
        r"презентац", r"powerpoint", r"\bpptx\b", r"слайд\w*",
    ],
    "3D/BIM/Revit": [
        r"\brevit\b", r"\bbim\b", r"3d[- ]?модел", r"визуализац\w* интерь", r"визуализац\w* экстерь",
    ],
    "CRM/1C/API интеграции": [
        r"\b1с\b", r"\bcrm\b", r"bitrix24", r"битрикс24", r"amo\s*crm", r"интеграц\w* api",
        r"rest api", r"webhook", r"вебхук",
    ],
}

STOPWORDS = {
    "нужно", "надо", "требуется", "работа", "сделать", "создать", "разработать", "для", "или",
    "как", "есть", "будет", "при", "это", "что", "под", "без", "все", "всё", "можно", "также",
    "необходимо", "задача", "проект", "ищем", "нужен", "нужна", "нужны", "срочно", "добрый",
    "день", "должен", "должна", "который", "которая", "которые", "только", "если", "после",
}


def text_of(p):
    return f"{p.get('title', '')} {p.get('description', '')}".lower()


def matches(text, pats):
    return any(re.search(p, text, re.I) for p in pats)


def budget(p):
    return p.get("max_budget") or p.get("price") or 0


def med(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return round(statistics.median(vals), 1) if vals else None


def make_example(p):
    return {
        "id": p.get("id"),
        "title": p.get("title"),
        "price": p.get("price"),
        "max_budget": p.get("max_budget"),
        "offers": p.get("offers"),
        "hire_rate": p.get("hire_rate"),
        "source_page": p.get("source_page"),
        "url": p.get("url"),
    }


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    projects = data.get("projects", [])
    total = len(projects)

    summary = {}
    for name, pats in CATEGORIES.items():
        rows = [p for p in projects if matches(text_of(p), pats)]
        rows_sorted = sorted(
            rows,
            key=lambda p: (
                (p.get("offers") is not None and p.get("offers") <= 3),
                budget(p),
                p.get("hire_rate") or 0,
                -(p.get("source_page") or 99),
            ),
            reverse=True,
        )
        summary[name] = {
            "count": len(rows),
            "share_pct": round(len(rows) * 100 / total, 1) if total else 0,
            "median_budget": med([budget(p) for p in rows if budget(p)]),
            "median_price": med([p.get("price") for p in rows if p.get("price")]),
            "median_offers": med([p.get("offers") for p in rows if isinstance(p.get("offers"), int)]),
            "zero_offers": sum(1 for p in rows if p.get("offers") == 0),
            "offers_le_3": sum(1 for p in rows if isinstance(p.get("offers"), int) and p.get("offers") <= 3),
            "budget_ge_10000": sum(1 for p in rows if budget(p) >= 10000),
            "budget_ge_30000": sum(1 for p in rows if budget(p) >= 30000),
            "examples": [make_example(p) for p in rows_sorted[:5]],
        }

    words = Counter()
    for p in projects:
        title = (p.get("title") or "").lower().replace("ё", "е")
        for w in re.findall(r"[a-zа-я0-9-]{4,}", title, re.I):
            if w not in STOPWORDS and not w.isdigit():
                words[w] += 1

    out = {
        "scraped_at": data.get("scraped_at"),
        "requested_pages": data.get("requested_pages"),
        "reported_total_pages": data.get("reported_total_pages"),
        "scanned_pages": data.get("scanned_pages"),
        "total_projects": total,
        "overall": {
            "median_budget": med([budget(p) for p in projects if budget(p)]),
            "median_price": med([p.get("price") for p in projects if p.get("price")]),
            "median_offers": med([p.get("offers") for p in projects if isinstance(p.get("offers"), int)]),
            "zero_offers": sum(1 for p in projects if p.get("offers") == 0),
            "offers_le_3": sum(1 for p in projects if isinstance(p.get("offers"), int) and p.get("offers") <= 3),
        },
        "categories": summary,
        "top_title_words": [{"word": w, "count": n} for w, n in words.most_common(40)],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Analysed {total} projects across {len(CATEGORIES)} market categories")


if __name__ == "__main__":
    main()
