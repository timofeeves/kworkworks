from __future__ import annotations

import asyncio
import json
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Page, async_playwright

KWORK_URL = os.getenv("KWORK_URL", "https://kwork.ru/projects?c=all")
PAGES_TO_SCAN = max(1, int(os.getenv("KWORK_PAGES", "3")))
DATA_DIR = Path("data")

EXTRACT_JS = r"""
() => {
  const money = (value) => {
    if (!value) return null;
    const digits = value.replace(/\s/g, '').match(/\d+/)?.[0];
    return digits ? Number(digits) : null;
  };

  const cards = [...document.querySelectorAll('.want-card.want-card--list')];

  const projects = cards.map((card) => {
    const titleLink = card.querySelector('.wants-card__header-title a[href*="/projects/"]');
    if (!titleLink) return null;

    const href = titleLink.getAttribute('href');
    const url = new URL(href, location.origin).href;
    const idMatch = url.match(/\/projects\/(\d+)/);
    const id = idMatch ? Number(idMatch[1]) : null;

    const descRoot = card.querySelector('.wants-card__description-text');
    const descriptions = descRoot
      ? [...descRoot.querySelectorAll('.breakwords.first-letter')]
      : [];

    const fullBlock = descriptions.at(-1) || null;
    const fullInline = fullBlock?.querySelector(':scope > .d-inline');
    let description = (fullInline?.innerText || fullBlock?.innerText || '').trim();
    description = description.replace(/\s*Скрыть\s*$/i, '').trim();

    const visibleText = card.innerText || '';

    const priceMatch = visibleText.match(
      /(?:Цена(?:\s+до:)?|Желаемый бюджет:\s*до)\s*([\d\s]+)\s*₽/i
    );
    const maxBudgetMatch = visibleText.match(
      /Допустимый:\s*до\s*([\d\s]+)\s*₽/i
    );
    const buyerProjectsMatch = visibleText.match(
      /Размещено проектов на бирже:\s*(\d+)/i
    );
    const hireRateMatch = visibleText.match(/Нанято:\s*(\d+)%/i);
    const offersMatch = visibleText.match(/Предложений:\s*(\d+)/i);
    const timeLeftMatch = visibleText.match(/Осталось:\s*([^\n]+)/i);

    const buyer = card.querySelector(
      '.want-payer-statistic a[href*="/user/"]'
    )?.innerText?.trim() || null;

    const files = [...card.querySelectorAll('.files-list .file-item .nowrap')]
      .map((el) => el.innerText.trim())
      .filter(Boolean);

    const externalLinks = descRoot
      ? [...descRoot.querySelectorAll('a[href^="http"]')]
          .map((a) => a.href)
          .filter(Boolean)
      : [];

    return {
      id,
      title: titleLink.innerText.trim(),
      url,
      description,
      price: money(priceMatch?.[1]),
      max_budget: money(maxBudgetMatch?.[1]),
      buyer,
      buyer_projects: buyerProjectsMatch ? Number(buyerProjectsMatch[1]) : null,
      hire_rate: hireRateMatch ? Number(hireRateMatch[1]) : null,
      offers: offersMatch ? Number(offersMatch[1]) : null,
      time_left: timeLeftMatch?.[1]?.trim() || null,
      files,
      external_links: [...new Set(externalLinks)],
    };
  }).filter(Boolean);

  const pageNumbers = [...document.querySelectorAll('.pagination__item')]
    .map((el) => Number(el.innerText.trim()))
    .filter(Number.isFinite);

  const activePage = Number(
    document.querySelector('.pagination__item.active')?.innerText?.trim()
  ) || 1;

  const totalPages = pageNumbers.length ? Math.max(...pageNumbers) : 1;

  return {
    projects,
    active_page: activePage,
    total_pages: totalPages,
    has_next: Boolean(document.querySelector('.pagination__arrow--next')),
  };
}
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


async def wait_for_projects(page: Page) -> None:
    await page.wait_for_selector(
        ".want-card.want-card--list .wants-card__header-title a",
        timeout=45_000,
    )


async def scrape() -> dict[str, Any]:
    scraped_at = utc_now()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="ru-RU",
            viewport={"width": 1440, "height": 1200},
        )
        page = await context.new_page()
        page.set_default_timeout(30_000)

        await page.goto(KWORK_URL, wait_until="domcontentloaded", timeout=60_000)
        await wait_for_projects(page)

        collected: dict[int, dict[str, Any]] = {}
        page_summaries: list[dict[str, Any]] = []
        seen_fingerprints: set[tuple[int | None, int | None]] = set()
        reported_total_pages = 1

        for scan_index in range(PAGES_TO_SCAN):
            payload = await page.evaluate(EXTRACT_JS)
            projects = payload["projects"]
            active_page = int(payload.get("active_page") or scan_index + 1)
            reported_total_pages = max(
                reported_total_pages,
                int(payload.get("total_pages") or 1),
            )

            first_id = projects[0]["id"] if projects else None
            fingerprint = (active_page, first_id)
            if fingerprint in seen_fingerprints:
                break
            seen_fingerprints.add(fingerprint)

            for project in projects:
                project["source_page"] = active_page
                if project["id"] is not None:
                    collected[int(project["id"])] = project

            page_summaries.append(
                {
                    "page": active_page,
                    "projects": len(projects),
                    "first_project_id": first_id,
                }
            )

            if active_page >= reported_total_pages:
                break
            if scan_index + 1 >= PAGES_TO_SCAN:
                break

            next_button = page.locator(".pagination__arrow--next")
            if await next_button.count() == 0:
                break

            previous_page = active_page
            previous_first_href = await page.locator(
                '.want-card.want-card--list .wants-card__header-title a'
            ).first.get_attribute("href")

            await next_button.click()

            try:
                await page.wait_for_function(
                    """
                    ([prevPage, prevHref]) => {
                      const active = Number(
                        document.querySelector('.pagination__item.active')?.innerText?.trim()
                      ) || 1;
                      const firstHref = document.querySelector(
                        '.want-card.want-card--list .wants-card__header-title a'
                      )?.getAttribute('href');
                      return active !== prevPage || firstHref !== prevHref;
                    }
                    """,
                    [previous_page, previous_first_href],
                    timeout=20_000,
                )
            except Exception:
                # Один дополнительный шанс для медленной Vue-перерисовки.
                await page.wait_for_timeout(2_000)

            await wait_for_projects(page)
            await page.wait_for_timeout(int(random.uniform(700, 1300)))

        await context.close()
        await browser.close()

    ordered = list(collected.values())
    ordered.sort(key=lambda p: (p.get("source_page", 9999), -(p.get("id") or 0)))

    return {
        "scraped_at": scraped_at,
        "source": KWORK_URL,
        "requested_pages": PAGES_TO_SCAN,
        "reported_total_pages": reported_total_pages,
        "scanned_pages": len(page_summaries),
        "page_summaries": page_summaries,
        "count": len(ordered),
        "projects": ordered,
    }


async def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    previous_seen = read_json(DATA_DIR / "seen_ids.json", {"ids": []})
    seen_ids = {int(x) for x in previous_seen.get("ids", []) if str(x).isdigit()}

    result = await scrape()
    projects = result["projects"]

    new_projects = [p for p in projects if int(p["id"]) not in seen_ids]
    current_ids = {int(p["id"]) for p in projects}
    all_seen = seen_ids | current_ids

    write_json(DATA_DIR / "projects.json", result)
    write_json(
        DATA_DIR / "new_projects.json",
        {
            "scraped_at": result["scraped_at"],
            "count": len(new_projects),
            "projects": new_projects,
        },
    )
    write_json(
        DATA_DIR / "seen_ids.json",
        {
            "updated_at": result["scraped_at"],
            "count": len(all_seen),
            "ids": sorted(all_seen),
        },
    )

    print(
        f"Kwork: scanned {result['scanned_pages']} page(s), "
        f"found {result['count']} project(s), "
        f"new {len(new_projects)}."
    )


if __name__ == "__main__":
    asyncio.run(main())
