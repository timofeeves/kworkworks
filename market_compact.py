import json
from pathlib import Path

SRC = Path("data/market_summary.json")
OUT = Path("data/market_summary_compact.json")

KEEP = (
    "title_count",
    "title_share_pct",
    "count",
    "share_pct",
    "median_budget",
    "median_price",
    "median_offers",
    "zero_offers",
    "offers_le_3",
    "budget_ge_10000",
    "budget_ge_30000",
)


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    compact = {
        "scraped_at": data.get("scraped_at"),
        "requested_pages": data.get("requested_pages"),
        "reported_total_pages": data.get("reported_total_pages"),
        "scanned_pages": data.get("scanned_pages"),
        "total_projects": data.get("total_projects"),
        "overall": data.get("overall", {}),
        "categories": {
            name: {k: row.get(k) for k in KEEP}
            for name, row in data.get("categories", {}).items()
        },
        "top_title_words": data.get("top_title_words", []),
    }
    OUT.write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote compact market summary for {len(compact['categories'])} categories")


if __name__ == "__main__":
    main()
