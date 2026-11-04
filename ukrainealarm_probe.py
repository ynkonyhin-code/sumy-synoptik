# -*- coding: utf-8 -*-
"""Діагностика Ukraine Alarm API для «Сумського синоптика» — ТІЛЬКИ ЧИТАЄ, нічого не публікує.

Що робить:
  1) знаходить у дереві регіонів Сумську область, її райони й громади (з ID);
  2) показує поточний стан тривог по Сумській області (сирий JSON);
  3) показує, які типи тривог і яка структура відповіді є в країні (кілька прикладів) — щоб побачити,
     чи є в API поділ «ракети / дрони», чи лише тип тривоги.
Ключ береться зі змінної середовища UKRAINEALARM_API_KEY (секрет GitHub) і ніколи не друкується.
"""
import json, os, sys, time
import requests

BASE = "https://api.ukrainealarm.com/api/v3"
KEY = os.getenv("UKRAINEALARM_API_KEY", "").strip()
if not KEY:
    sys.exit("❌ Не задано секрет UKRAINEALARM_API_KEY")
H = {"Authorization": KEY, "Accept": "application/json"}


def get(path):
    for attempt in range(3):
        r = requests.get(BASE + path, headers=H, timeout=30)
        print(f"GET {path} -> HTTP {r.status_code}, {len(r.content)} байт, "
              f"ліміти: { {k: v for k, v in r.headers.items() if 'limit' in k.lower() or 'retry' in k.lower()} }")
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 5)) + 1); continue
        r.raise_for_status()
        return r.json()
    raise SystemExit("Забагато запитів (429)")


def walk(node, depth=0):
    """Обхід дерева регіонів: віддає (рівень, словник)."""
    if isinstance(node, list):
        for x in node:
            yield from walk(x, depth)
    elif isinstance(node, dict):
        yield depth, node
        for k, v in node.items():
            if isinstance(v, (list, dict)) and k.lower().startswith("regionchild") or k in ("states", "districts", "communities", "children"):
                yield from walk(v, depth + 1)


print("═══ 1. ДЕРЕВО РЕГІОНІВ: Сумська область ═══")
regions = get("/regions")
sumy_state = None
for _, n in walk(regions):
    if "Сумська" in str(n.get("regionName", "")):
        sumy_state = n; break
if not sumy_state:
    print("Сумську область не знайдено. Перші 1500 символів відповіді:\n", json.dumps(regions, ensure_ascii=False)[:1500])
    sys.exit(1)
ids = set()
print("Область:", sumy_state.get("regionId"), sumy_state.get("regionName"), sumy_state.get("regionType"))
for lvl, n in walk(sumy_state.get("regionChildIds", [])):
    ids.add(str(n.get("regionId")))
    if str(n.get("regionType")) != "Community":                    # громади (їх багато) не друкуємо, лише райони
        print("  " * (lvl + 1) + f"{n.get('regionId')}  {n.get('regionName')}  [{n.get('regionType')}]")
ids.add(str(sumy_state.get("regionId")))
print(f"(усього вузлів у області разом із громадами: {len(ids)})")
# окремо — Сумський район і його громади, щоб побачити, чи Суми — громада всередині
for _, n in walk(sumy_state.get("regionChildIds", [])):
    if "Сумськ" in str(n.get("regionName", "")):
        kids = [(c.get("regionId"), c.get("regionName")) for _, c in walk(n.get("regionChildIds", []))]
        print(f"\n  >> {n.get('regionName')} ({n.get('regionId')}) містить {len(kids)} вузлів, напр.: {kids[:6]}")

print("\n═══ 2. ПОТОЧНА ТРИВОГА: Сумська область ═══")
print(json.dumps(get(f"/alerts/{sumy_state['regionId']}"), ensure_ascii=False, indent=1)[:3500])

print("\n═══ 3. УСІ АКТИВНІ ТРИВОГИ В КРАЇНІ (структура й типи) ═══")
alerts = get("/alerts")
types = {}
for reg in alerts if isinstance(alerts, list) else []:
    for a in reg.get("activeAlerts", []):
        types[a.get("type")] = types.get(a.get("type"), 0) + 1
print("Регіонів із тривогою зараз:", len(alerts) if isinstance(alerts, list) else "?", "| типи тривог:", types or "жодної")
print("Приклади записів:\n", json.dumps(alerts[:3] if isinstance(alerts, list) else alerts, ensure_ascii=False, indent=1)[:3000])
mine = [r for r in alerts if str(r.get("regionId")) in ids] if isinstance(alerts, list) else []
print("\nУ Сумській області зараз:", json.dumps(mine, ensure_ascii=False, indent=1)[:2000] if mine else "тривог немає")

print("\n═══ 4. СТАТУС (індекс останньої зміни) ═══")
print(json.dumps(get("/alerts/status"), ensure_ascii=False))
