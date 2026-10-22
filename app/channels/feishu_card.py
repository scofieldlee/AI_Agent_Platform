"""Feishu interactive-card renderer for RichMessage (P1: lark_md + link buttons)."""

import json
from typing import Dict

from app.channels.rich_message import THEME_MAP_FEISHU, guard_length, prepare


def render_feishu_card(msg) -> str:
    """Render a RichMessage into a Feishu interactive card JSON string.

    Feishu card notes:
    - lark_md supports bold/italic/links/lists/quotes/images — no tables
      (tables are demoted to lists).
    - Card size limit is ~30KB; long content is guarded.
    """
    body, buttons = prepare(msg)
    body_for_card = guard_length(body, max_chars=6000)

    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": body_for_card}}]
    action_btns, url_btns = [], []
    for b in buttons:
        if b.url:
            url_btns.append({"tag": "button",
                             "text": {"tag": "plain_text", "content": b.text},
                             "type": "primary",
                             "url": b.url})
        elif b.action:
            action_btns.append({"tag": "button",
                                "text": {"tag": "plain_text", "content": b.text},
                                "type": "default",
                                "value": {"action": b.action, **(b.payload or {})}})
    if action_btns:
        elements.append({"tag": "hr"})
        elements.append({"tag": "action", "actions": action_btns})
    if url_btns:
        elements.append({"tag": "action", "actions": url_btns})

    card: Dict = {
        "config": {"wide_screen_mode": True},
        "elements": elements,
    }
    if msg.header:
        card["header"] = {
            "template": THEME_MAP_FEISHU.get(msg.theme, "blue"),
            "title": {"tag": "plain_text", "content": msg.header[:80]},
        }

    return json.dumps(card, ensure_ascii=False)
