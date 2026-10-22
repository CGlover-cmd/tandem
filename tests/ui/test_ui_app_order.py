from __future__ import annotations

import json
from pathlib import Path

from tandem.ui.app_order import MAX_APPS, AppOrderStore, arrange
from tandem.ui.backend import AppInfo

APPS = [
    AppInfo("com.example.b", "Bravo"),
    AppInfo("com.example.a", "alpha"),
    AppInfo("com.example.c", "Charlie"),
]


def test_arrange_follows_the_saved_order_then_adds_new_apps_by_name() -> None:
    assert [a.id for a in arrange(APPS, [])] == ["com.example.a", "com.example.b", "com.example.c"]
    saved = ["com.example.c", "com.example.gone", "com.example.b"]
    assert [a.id for a in arrange(APPS, saved)] == [
        "com.example.c",
        "com.example.b",
        "com.example.a",  # new since the order was saved
    ]


def test_orders_survive_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "ui" / "app-order.json"
    AppOrderStore(path).set_order("dev-1", ["x", "y", "x"])
    assert AppOrderStore(path).order("dev-1") == ["x", "y"]
    assert AppOrderStore(path).order("dev-2") == []


def test_orders_are_capped(tmp_path: Path) -> None:
    store = AppOrderStore()
    store.set_order("dev-1", [f"app{n}" for n in range(MAX_APPS + 10)])
    assert len(store.order("dev-1")) == MAX_APPS


def test_unreadable_or_odd_files_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "app-order.json"
    path.write_text("{oops", encoding="utf-8")
    assert AppOrderStore(path).order("dev-1") == []
    path.write_text(json.dumps([1, 2]), encoding="utf-8")
    assert AppOrderStore(path).order("dev-1") == []
    path.write_text(json.dumps({"dev-1": ["a", 3, "b"], "dev-2": "nope"}), encoding="utf-8")
    store = AppOrderStore(path)
    assert store.order("dev-1") == ["a", "b"]
    assert store.order("dev-2") == []


def test_a_failed_save_keeps_the_order_in_memory(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    store = AppOrderStore(blocker / "app-order.json")  # its folder can't be made
    store.set_order("dev-1", ["a"])
    assert store.order("dev-1") == ["a"]
