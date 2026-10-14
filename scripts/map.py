"""نقشه‌ی پروژه را می‌سازد: docs/graph.json

خروجی شامل این موارد است (همه از روی فایل‌ها خوانده می‌شود، چیزی حدس زده نمی‌شود):
  - ماژول‌ها: فایل، تعداد خط، تعداد تابع و کلاس، و وابستگی‌های داخلی (from . import ...)
  - جدول‌های دیتابیس: از دستورهای CREATE TABLE در app/db.py
  - نقطه‌های ورود: فایل‌هایی که بلوک __main__ دارند و دستورهای Dockerfile/systemd که آن‌ها را اجرا می‌کنند

اجرا:  python scripts/map.py
"""
from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
OUT = ROOT / "docs" / "graph.json"
INTERNAL = re.compile(r"^from \.(\w*) import (.+)$|^from \. import (.+)$", re.M)


def module_info(path: Path) -> dict:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    deps = set()
    for m in INTERNAL.finditer(src):
        if m.group(1):
            deps.add(m.group(1))
        else:
            names = m.group(3) or m.group(2) or ""
            deps.update(n.strip().split(" as ")[0] for n in names.split(",") if n.strip())
    funcs = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    return {
        "file": str(path.relative_to(ROOT)).replace("\\", "/"),
        "lines": src.count("\n") + 1,
        "functions": funcs,
        "classes": classes,
        "imports_internal": sorted(d for d in deps if d and d != path.stem),
        "entry_point": '__name__ == "__main__"' in src,
    }


def db_tables() -> list:
    src = (APP / "db.py").read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+)\(", src):
        name = m.group(1)
        # ستون‌ها: خط‌های بعد از CREATE تا «);» (اولین نام کلیدواژه‌ها حذف می‌شود)
        body = src[m.end(): src.find(");", m.end())]
        cols = []
        for line in body.splitlines():
            line = line.split("--")[0]
            # چند ستون ممکن است در یک خط باشند؛ هر تکه‌ی جدا شده با ویرگول را بررسی می‌کنیم
            for piece in line.split(","):
                words = piece.strip().split()
                if not words:
                    continue
                first = words[0].strip("()")
                if first.upper() in ("PRIMARY", "UNIQUE", "CHECK", "FOREIGN", "CREATE", "INSERT"):
                    continue
                if first and first[0].isalpha() and first not in cols:
                    cols.append(first)
        out.append({"table": name, "columns": cols})
    return out


def entry_points() -> dict:
    refs = {}
    for f in [ROOT / "Dockerfile", *sorted((ROOT / "deploy").glob("*.service"))]:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if "app." in line and ("python" in line or "ExecStart" in line or "CMD" in line):
                refs.setdefault(str(f.relative_to(ROOT)).replace("\\", "/"), []).append(line.strip())
    return refs


def main():
    modules = [module_info(p) for p in sorted(APP.glob("*.py")) if p.name != "__init__.py"]
    graph = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "scripts/map.py",
        "modules": modules,
        "tables": db_tables(),
        "entry_points": {
            "bot": "app/main.py",
            "panel": "app/panel.py",
            "run_references": entry_points(),
        },
        "tests": sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "tests").glob("test_*.py")),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"نوشته شد: {OUT.relative_to(ROOT)}  ({len(modules)} ماژول، {len(graph['tables'])} جدول)")


if __name__ == "__main__":
    main()
