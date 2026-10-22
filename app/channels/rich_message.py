"""Unified rich-message IR (intermediate representation) for IM channels.

Upstream producers (workflow replies, employee progress, notices) build a
RichMessage without knowing the target channel; each channel adapter renders
it into its native card format (Feishu interactive card / DingTalk
markdown & actionCard).

P1 supports link-type buttons only (jump URL, no callback needed).
"""

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Button:
    """A card button.

    - Link type (P1): url set, click jumps to the URL.
    - Action type (P2): action set, click triggers a card callback
      (Feishu only; requires card_encrypt_key/card_verification_token).
    """

    text: str
    url: Optional[str] = None
    action: Optional[str] = None              # transfer_human | reply_prompt
    payload: dict = field(default_factory=dict)


# Supported callback actions (P2)
CARD_ACTIONS = {"transfer_human", "reply_prompt"}


def sign_action(channel_id: int, payload: dict, secret: str) -> str:
    """HMAC-SHA256 signature over channel/payload for callback verification."""
    raw = (f"{channel_id}:{payload.get('action', '')}:"
           f"{payload.get('conversation_id', '')}:{payload.get('prompt', '')}")
    return hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:24]


def verify_action(channel_id: int, payload: dict, sig: str, secret: str) -> bool:
    if not sig or not secret:
        return False
    return hmac.compare_digest(sign_action(channel_id, payload, secret), sig)


@dataclass
class RichMessage:
    """Channel-agnostic rich message."""

    markdown: str
    header: Optional[str] = None            # card title, e.g. "🤖 AI 助手"
    theme: str = "default"                  # default / success / warning / error
    buttons: list = field(default_factory=list)  # list[Button]
    disable_url_promotion: bool = False     # skip auto URL->button promotion


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

_MD_LINK_RE = re.compile(r"\[([^\]]{1,80})\]\((https?://[^\s)]+)\)")
_BARE_URL_RE = re.compile(r"(?<![\"'(=\]>])(https?://[^\s<>\"')\]]+)")


def extract_urls(markdown: str, max_buttons: int = 3) -> list:
    """Extract distinct URLs from a markdown text for button promotion.

    Prefers labeled links ([text](url)) over bare URLs; dedupes by URL.
    """
    buttons, seen = [], set()
    for m in _MD_LINK_RE.finditer(markdown):
        url = m.group(2)
        if url in seen:
            continue
        seen.add(url)
        buttons.append(Button(text=m.group(1)[:20] or "查看链接", url=url))
        if len(buttons) >= max_buttons:
            return buttons
    for m in _BARE_URL_RE.finditer(markdown):
        url = m.group(1)
        if url in seen:
            continue
        seen.add(url)
        # Bare URL: keep the URL itself (truncated) as the label
        short = re.sub(r"^https?://", "", url)
        buttons.append(Button(text=short[:20] or "查看链接", url=url))
        if len(buttons) >= max_buttons:
            break
    return buttons


def prepare(msg) -> tuple:
    """Preprocess a RichMessage for rendering.

    Returns (body_markdown, buttons): tables demoted, URLs promoted to
    buttons (unless disabled), promoted URLs stripped from the body.
    """
    body = demote_tables(msg.markdown)
    buttons = list(msg.buttons)
    if not msg.disable_url_promotion:
        promoted = [b for b in extract_urls(body) if b not in buttons]
        if promoted:
            buttons = (buttons + promoted)[:3]
            body = strip_promoted(body, [b.url for b in promoted])
    return body, buttons


def strip_markdown_links(markdown: str) -> str:
    """Replace labeled links with their text (URL moved to button area)."""
    return _MD_LINK_RE.sub(r"\1", markdown)


def strip_promoted(markdown: str, promoted_urls: list) -> str:
    """Remove promoted URLs from the body after button promotion.

    - Labeled links [text](url) → text only
    - Bare URLs → a short pointer to the button area
    """
    out = _MD_LINK_RE.sub(r"\1", markdown)
    for url in promoted_urls:
        # Remove a bare URL occurrence (possibly following "：" or spaces)
        out = re.sub(
            r"(https?://" + re.escape(url.split("://", 1)[1]) + r")",
            "*详见下方按钮*",
            out,
        )
    return out


THEME_MAP_FEISHU = {
    "default": "blue",
    "success": "green",
    "warning": "orange",
    "error": "red",
}

THEME_EMOJI_DINGTALK = {
    "default": "🤖",
    "success": "✅",
    "warning": "⚠️",
    "error": "❌",
}


def guard_length(markdown: str, max_chars: int = 8000,
                 full_url: Optional[str] = None) -> str:
    """Trim overly long markdown for card size limits (Feishu card ≤ 30KB).

    Appends a pointer to the full content when truncating.
    """
    if len(markdown) <= max_chars:
        return markdown
    trimmed = markdown[:max_chars].rsplit("\n", 1)[0] + "\n\n……（内容过长已截断）"
    if full_url:
        trimmed += f"\n[查看全文]({full_url})"
    return trimmed


def demote_tables(markdown: str) -> str:
    """Convert markdown tables to plain lists for renderers without table
    support (both Feishu card lark_md and DingTalk markdown lack tables).

    A 2-column table becomes '**key**：value' lines; wider tables become
    'cell1 | cell2 | ...' lines. Separator rows are dropped.
    """
    lines = markdown.split("\n")
    out, table_buf = [], []

    def flush_table():
        if not table_buf:
            return
        rows = []
        for line in table_buf:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue  # separator row
            rows.append(cells)
        if len(rows) == 1:
            out.append(" · " + " | ".join(rows[0]))
        elif len(rows) >= 2:
            header, body = rows[0], rows[1:]
            if len(header) == 2:
                for row in body:
                    out.append(f"**{row[0]}**：{row[1] if len(row) > 1 else ''}")
            else:
                for row in body:
                    out.append(" · " + " | ".join(row))
        table_buf.clear()

    for line in lines:
        if line.strip().startswith("|") and line.strip().endswith("|"):
            table_buf.append(line)
        else:
            flush_table()
            out.append(line)
    flush_table()
    return "\n".join(out)
