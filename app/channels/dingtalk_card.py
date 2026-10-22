"""DingTalk card renderers for RichMessage (P1: sampleMarkdown / sampleActionCard)."""

from app.channels.rich_message import THEME_EMOJI_DINGTALK, guard_length, prepare


def render_dingtalk_markdown(msg) -> dict:
    """Render a RichMessage into DingTalk `sampleMarkdown` msgParam.

    msgParam: {"title": ..., "text": ...} — text is markdown rendered by
    DingTalk (bold/italic/links/quotes/images; NO tables → demoted).
    """
    body, _buttons = prepare(msg)
    body = guard_length(body, max_chars=5000)

    prefix = THEME_EMOJI_DINGTALK.get(msg.theme, "🤖")
    title = f"{prefix} {msg.header[:40]}" if msg.header else f"{prefix} AI 助手"
    text = f"### {title}\n\n{body}" if msg.header else f"{prefix} {body}"

    return {"title": title[:50], "text": text}


def render_dingtalk_actioncard(msg) -> dict:
    """Render a RichMessage into DingTalk `sampleActionCard` msgParam
    (markdown body + link buttons).

    msgParam: {"title": ..., "text": ..., "btnOrientation": "0",
               "btns": [{"title": ..., "actionURL": ...}]}
    """
    body, buttons = prepare(msg)
    body = guard_length(body, max_chars=5000)

    prefix = THEME_EMOJI_DINGTALK.get(msg.theme, "🤖")
    title = f"{prefix} {msg.header[:40]}" if msg.header else f"{prefix} AI 助手"

    btns = [
        {"title": b.text[:20], "actionURL": b.url}
        for b in buttons if b.url
    ][:3]

    param = {
        "title": title[:50],
        "text": f"### {title}\n\n{body}" if msg.header else f"{prefix} {body}",
        "btnOrientation": "0",
        "btns": btns,
    }
    return param
