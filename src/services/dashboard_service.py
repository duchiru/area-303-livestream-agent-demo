# Copyright (C) 2026 Nguyen The Viet, Vu Thi Mai Anh, Do Huu An Phu, Phan Thuy Tram
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Service for inspecting, managing, mutating, and purging generated livestream data."""

import datetime
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.learner import default_learning_state
from .session_service import session_service
from .shop_service import shop_service

_PLAYBOOK_FILENAME_RE = re.compile(r"^playbook_\d{14}\.json$")
_REVIEW_FILENAME_RE = re.compile(r"^review_\d{14}\.json$")


class DashboardService:
    """Provides file management, inspection, mutation, and purging for generated data."""

    def _validate_playbook_filename(self, filename: str) -> str:
        f = str(filename or "").strip()
        if not _PLAYBOOK_FILENAME_RE.match(f):
            raise ValueError(f"Invalid playbook filename: '{filename}'. Expected format: playbook_YYYYMMDDHHMMSS.json")
        return f

    def _validate_review_filename(self, filename: str) -> str:
        f = str(filename or "").strip()
        if not _REVIEW_FILENAME_RE.match(f):
            raise ValueError(f"Invalid review filename: '{filename}'. Expected format: review_YYYYMMDDHHMMSS.json")
        return f

    def get_shop_data_summary(self, shop_id: str) -> Dict[str, Any]:
        """Collects summary statistics on all generated files for a shop."""
        sid = shop_service.validate_shop_id(shop_id)
        shop_dir = shop_service.get_shop_dir(sid)

        # Draft playbook
        draft_file = shop_dir / "draft_playbook.json"
        draft_summary = None
        try:
            data = json.loads(draft_file.read_text(encoding="utf-8"))
            draft_summary = {
                "exists": True,
                "updated_at": data.get("updated_at"),
                "slot": data.get("slot"),
                "items_count": len(data.get("items") or []),
                "combos_count": len(data.get("combos") or []),
                "vouchers_count": len(data.get("vouchers") or []),
                "size_bytes": draft_file.stat().st_size,
            }
        except FileNotFoundError:
            pass
        except Exception:
            draft_summary = {"exists": True, "corrupted": True, "size_bytes": draft_file.stat().st_size}

        # Orders
        orders_file = shop_dir / "orders.json"
        orders_summary = {"exists": False, "count": 0, "gmv": 0.0, "size_bytes": 0}
        try:
            orders = json.loads(orders_file.read_text(encoding="utf-8"))
            total_gmv = sum(float(o.get("price", 0.0) or 0.0) * int(o.get("quantity", 1) or 1) for o in orders)
            orders_summary = {
                "exists": True,
                "count": len(orders),
                "gmv": total_gmv,
                "size_bytes": orders_file.stat().st_size,
            }
        except FileNotFoundError:
            pass
        except Exception:
            orders_summary = {"exists": True, "corrupted": True, "count": 0, "gmv": 0.0, "size_bytes": orders_file.stat().st_size}

        # Learner State
        learner_file = shop_dir / "learning_state.json"
        learner_summary = {"exists": False, "alpha": 0.5, "beta": 0.2, "n_sessions": 0, "size_bytes": 0}
        try:
            l_state = json.loads(learner_file.read_text(encoding="utf-8"))
            params = l_state.get("params") or {}
            metrics = l_state.get("metrics") or {}
            learner_summary = {
                "exists": True,
                "alpha": params.get("alpha", 0.5),
                "beta": params.get("beta", 0.2),
                "rolling_mape": metrics.get("rolling_mape"),
                "n_sessions": metrics.get("n_sessions", 0),
                "history_count": len(l_state.get("history") or []),
                "size_bytes": learner_file.stat().st_size,
            }
        except FileNotFoundError:
            pass
        except Exception:
            learner_summary = {"exists": True, "corrupted": True, "size_bytes": learner_file.stat().st_size}

        # Archived Playbooks
        playbooks_dir = shop_dir / "playbooks"
        archived_playbooks_count = 0
        archived_playbooks_bytes = 0
        if playbooks_dir.exists():
            for p in playbooks_dir.glob("playbook_*.json"):
                archived_playbooks_count += 1
                archived_playbooks_bytes += p.stat().st_size

        # Archived Reviews
        reviews_dir = shop_dir / "reviews"
        archived_reviews_count = 0
        archived_reviews_bytes = 0
        if reviews_dir.exists():
            for r in reviews_dir.glob("review_*.json"):
                archived_reviews_count += 1
                archived_reviews_bytes += r.stat().st_size

        total_files = (1 if draft_summary and draft_summary.get("exists") else 0) + \
                      (1 if orders_summary.get("exists") else 0) + \
                      (1 if learner_summary.get("exists") else 0) + \
                      archived_playbooks_count + archived_reviews_count

        total_bytes = (draft_summary.get("size_bytes", 0) if draft_summary else 0) + \
                      orders_summary.get("size_bytes", 0) + \
                      learner_summary.get("size_bytes", 0) + \
                      archived_playbooks_bytes + archived_reviews_bytes

        return {
            "shop_id": sid,
            "total_files": total_files,
            "total_bytes": total_bytes,
            "draft_playbook": draft_summary,
            "orders": orders_summary,
            "learning_state": learner_summary,
            "archived_playbooks_count": archived_playbooks_count,
            "archived_playbooks_bytes": archived_playbooks_bytes,
            "archived_reviews_count": archived_reviews_count,
            "archived_reviews_bytes": archived_reviews_bytes,
        }

    # Playbook Operations
    def list_archived_playbooks(self, shop_id: str) -> List[Dict[str, Any]]:
        sid = shop_service.validate_shop_id(shop_id)
        shop_dir = shop_service.get_shop_dir(sid)
        p_dir = shop_dir / "playbooks"
        results = []
        if p_dir.exists():
            for p in sorted(p_dir.glob("playbook_*.json"), key=lambda f: f.name, reverse=True):
                info = {
                    "filename": p.name,
                    "size_bytes": p.stat().st_size,
                    "created_at": None,
                    "slot": None,
                    "items_count": 0,
                    "combos_count": 0,
                }
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    info["created_at"] = data.get("updated_at")
                    info["slot"] = data.get("slot")
                    info["live_date"] = data.get("live_date")
                    info["items_count"] = len(data.get("items") or [])
                    info["combos_count"] = len(data.get("combos") or [])
                except Exception:
                    pass
                results.append(info)
        return results

    def get_playbook_detail(self, shop_id: str, filename: str) -> Dict[str, Any]:
        sid = shop_service.validate_shop_id(shop_id)
        valid_name = self._validate_playbook_filename(filename)
        path = shop_service.get_shop_dir(sid) / "playbooks" / valid_name
        if not path.exists():
            raise FileNotFoundError(f"Archived playbook '{filename}' not found.")
        return json.loads(path.read_text(encoding="utf-8"))

    def restore_playbook(self, shop_id: str, filename: str) -> Dict[str, Any]:
        """Restores an archived playbook as the current active draft_playbook.json."""
        sid = shop_service.validate_shop_id(shop_id)
        valid_name = self._validate_playbook_filename(filename)
        shop_dir = shop_service.get_shop_dir(sid)
        src_path = shop_dir / "playbooks" / valid_name
        if not src_path.exists():
            raise FileNotFoundError(f"Archived playbook '{filename}' not found.")

        dest_path = shop_dir / "draft_playbook.json"
        data = json.loads(src_path.read_text(encoding="utf-8"))
        data["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        data["restored_from"] = valid_name
        dest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    def delete_archived_playbook(self, shop_id: str, filename: str) -> bool:
        sid = shop_service.validate_shop_id(shop_id)
        valid_name = self._validate_playbook_filename(filename)
        path = shop_service.get_shop_dir(sid) / "playbooks" / valid_name
        if path.exists():
            path.unlink()
            return True
        return False

    def delete_draft_playbook(self, shop_id: str) -> bool:
        sid = shop_service.validate_shop_id(shop_id)
        path = shop_service.get_shop_dir(sid) / "draft_playbook.json"
        if path.exists():
            path.unlink()
            return True
        return False

    # Orders Operations
    def get_orders(self, shop_id: str) -> List[Dict[str, Any]]:
        sid = shop_service.validate_shop_id(shop_id)
        return session_service.get_onair_orders(sid)

    def update_order(self, shop_id: str, order_id: str, new_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        sid = shop_service.validate_shop_id(shop_id)
        shop_dir = shop_service.get_shop_dir(sid)
        path = shop_dir / "orders.json"
        orders = session_service.get_onair_orders(sid)
        found = False
        for o in orders:
            if str(o.get("order_id")) == str(order_id):
                found = True
                if "product_name" in new_data:
                    o["product_name"] = str(new_data["product_name"])
                if "price" in new_data:
                    o["price"] = float(new_data["price"])
                if "quantity" in new_data:
                    o["quantity"] = int(new_data["quantity"])
                break

        if not found:
            raise KeyError(f"Order '{order_id}' not found.")

        path.write_text(json.dumps(orders, ensure_ascii=False, indent=2), encoding="utf-8")
        return orders

    def delete_order(self, shop_id: str, order_id: str) -> List[Dict[str, Any]]:
        sid = shop_service.validate_shop_id(shop_id)
        shop_dir = shop_service.get_shop_dir(sid)
        path = shop_dir / "orders.json"
        orders = session_service.get_onair_orders(sid)
        filtered = [o for o in orders if str(o.get("order_id")) != str(order_id)]
        if len(filtered) == len(orders):
            raise KeyError(f"Order '{order_id}' not found.")
        path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
        return filtered

    def clear_orders(self, shop_id: str) -> bool:
        sid = shop_service.validate_shop_id(shop_id)
        session_service.clear_onair_orders(sid)
        return True

    # Learner State Operations
    def get_learner_state(self, shop_id: str) -> Dict[str, Any]:
        sid = shop_service.validate_shop_id(shop_id)
        return shop_service.load_learning_state(sid)

    def update_learner_params(self, shop_id: str, alpha: float, beta: float) -> Dict[str, Any]:
        sid = shop_service.validate_shop_id(shop_id)
        state = shop_service.load_learning_state(sid)
        a_min, a_max = state.get("bounds", {}).get("alpha", [0.1, 1.0])
        b_min, b_max = state.get("bounds", {}).get("beta", [0.05, 0.5])

        if not (a_min <= alpha <= a_max):
            raise ValueError(f"Alpha must be between {a_min} and {a_max}")
        if not (b_min <= beta <= b_max):
            raise ValueError(f"Beta must be between {b_min} and {b_max}")

        state.setdefault("params", {})
        state["params"]["alpha"] = round(float(alpha), 4)
        state["params"]["beta"] = round(float(beta), 4)
        shop_service.save_learning_state(sid, state)
        return state

    def reset_learner_state(self, shop_id: str) -> Dict[str, Any]:
        sid = shop_service.validate_shop_id(shop_id)
        fresh_state = default_learning_state()
        shop_service.save_learning_state(sid, fresh_state)
        return fresh_state

    # Reviews Operations
    def list_archived_reviews(self, shop_id: str) -> List[Dict[str, Any]]:
        sid = shop_service.validate_shop_id(shop_id)
        shop_dir = shop_service.get_shop_dir(sid)
        r_dir = shop_dir / "reviews"
        results = []
        if r_dir.exists():
            for r in sorted(r_dir.glob("review_*.json"), key=lambda f: f.name, reverse=True):
                info = {
                    "filename": r.name,
                    "size_bytes": r.stat().st_size,
                    "session_id": None,
                    "date": None,
                    "sku_count": 0,
                }
                try:
                    data = json.loads(r.read_text(encoding="utf-8"))
                    info["session_id"] = data.get("session_id")
                    info["date"] = data.get("date")
                    info["sku_count"] = len(data.get("actual") or [])
                except Exception:
                    pass
                results.append(info)
        return results

    def get_review_detail(self, shop_id: str, filename: str) -> Dict[str, Any]:
        sid = shop_service.validate_shop_id(shop_id)
        valid_name = self._validate_review_filename(filename)
        path = shop_service.get_shop_dir(sid) / "reviews" / valid_name
        if not path.exists():
            raise FileNotFoundError(f"Archived review '{filename}' not found.")
        return json.loads(path.read_text(encoding="utf-8"))

    def delete_archived_review(self, shop_id: str, filename: str) -> bool:
        sid = shop_service.validate_shop_id(shop_id)
        valid_name = self._validate_review_filename(filename)
        path = shop_service.get_shop_dir(sid) / "reviews" / valid_name
        if path.exists():
            path.unlink()
            return True
        return False

    # Purge Operations
    def purge_all_generated(self, shop_id: str) -> Dict[str, Any]:
        """Purges test session data (draft, orders, playbooks, reviews) while preserving shop data CSV and config."""
        sid = shop_service.validate_shop_id(shop_id)
        shop_dir = shop_service.get_shop_dir(sid)

        deleted_items = []
        # draft
        draft = shop_dir / "draft_playbook.json"
        if draft.exists():
            draft.unlink()
            deleted_items.append("draft_playbook.json")

        # orders
        orders = shop_dir / "orders.json"
        if orders.exists():
            orders.unlink()
            deleted_items.append("orders.json")

        # playbooks
        p_dir = shop_dir / "playbooks"
        p_count = 0
        if p_dir.exists():
            for p in p_dir.glob("playbook_*.json"):
                p.unlink()
                p_count += 1
            deleted_items.append(f"{p_count} playbooks")

        # reviews
        r_dir = shop_dir / "reviews"
        r_count = 0
        if r_dir.exists():
            for r in r_dir.glob("review_*.json"):
                r.unlink()
                r_count += 1
            deleted_items.append(f"{r_count} reviews")

        # reset learner state
        self.reset_learner_state(sid)
        deleted_items.append("reset learning_state.json to default")

        return {
            "status": "ok",
            "shop_id": sid,
            "deleted_items": deleted_items,
        }


dashboard_service = DashboardService()
