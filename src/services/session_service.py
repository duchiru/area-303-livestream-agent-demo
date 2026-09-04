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

"""Session service managing live drafts, active run-of-show playbooks, order tracking, and feedback."""

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.learner import update_learning_state
from .shop_service import shop_service


class SessionService:
    """Service managing session lifecycle states (Pre-live draft -> On-air -> Post-live review)."""

    def save_draft_playbook(self, shop_id: str, playbook_data: Dict[str, Any]) -> Path:
        """Saves active live draft playbook from Pre-live planner."""
        shop_d = shop_service.get_shop_dir(shop_id)
        path = shop_d / "draft_playbook.json"
        playbook_data["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        path.write_text(json.dumps(playbook_data, ensure_ascii=False, indent=2), encoding="utf-8")

        # Also save archive snapshot
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
        archive_path = shop_d / "playbooks" / f"playbook_{ts}.json"
        archive_path.write_text(json.dumps(playbook_data, ensure_ascii=False, indent=2), encoding="utf-8")

        return path

    def get_draft_playbook(self, shop_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves currently active draft playbook for On-air assistant."""
        shop_d = shop_service.get_shop_dir(shop_id)
        path = shop_d / "draft_playbook.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None

    def log_onair_order(self, shop_id: str, order_item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Appends a new order to the live on-air order tracker log."""
        shop_d = shop_service.get_shop_dir(shop_id)
        path = shop_d / "orders.json"
        try:
            orders = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            orders = []

        order_record = {
            "order_id": f"ORD_{datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S%f')[:10]}",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "item_id": order_item.get("item_id"),
            "product_name": order_item.get("product_name"),
            "price": float(order_item.get("price", 0.0)),
            "quantity": int(order_item.get("quantity", 1)),
            "combo_id": order_item.get("combo_id"),
            "voucher_applied": order_item.get("voucher_applied", False),
        }
        orders.append(order_record)
        path.write_text(json.dumps(orders, ensure_ascii=False, indent=2), encoding="utf-8")
        return orders

    def get_onair_orders(self, shop_id: str) -> List[Dict[str, Any]]:
        """Retrieves logged on-air orders."""
        shop_d = shop_service.get_shop_dir(shop_id)
        path = shop_d / "orders.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []

    def clear_onair_orders(self, shop_id: str) -> None:
        """Clears logged orders for a new session."""
        shop_d = shop_service.get_shop_dir(shop_id)
        path = shop_d / "orders.json"
        if path.exists():
            path.unlink()

    def submit_postlive_feedback(self, shop_id: str, feedback_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Processes actual live performance, updates learning state, and saves post-live review."""
        current_state = shop_service.load_learning_state(shop_id)
        new_state = update_learning_state(current_state, feedback_payload)
        shop_service.save_learning_state(shop_id, new_state)

        # Save post-live review record
        shop_d = shop_service.get_shop_dir(shop_id)
        review_dir = shop_d / "reviews"
        review_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
        review_path = review_dir / f"review_{ts}.json"
        review_path.write_text(json.dumps(feedback_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        return new_state


session_service = SessionService()
