"""
EMMA on Telegram: one bot for everyone.

Each message is matched to the EMMA login its Telegram account is linked
to (see links.py), then sent through the same POST /chat the website uses,
with a fresh token for that login. So the bot can never show or change
more than that person could on the website. Unlinked accounts get only
instructions for linking. Group chats are ignored, so data never lands
where other people can read it.

Changes EMMA proposes come back as messages with Confirm / Cancel
buttons; only the same Telegram account can press them.

Runs inside the API process (long polling, so no public URL is needed)
when TELEGRAM_BOT_TOKEN is set and TELEGRAM_BOT_FOR matches APP_INSTANCE.
Only one process may poll a given bot token at a time.
"""
import asyncio
import html
import logging
import re
import secrets
import time
from collections import defaultdict, deque

import httpx
from starlette.concurrency import run_in_threadpool

from .. import notify
from ..config import settings
from ..security import create_access_token
from . import links

log = logging.getLogger("emma.telegram")

HISTORY = 20
ACTION_SECONDS = 600
LINK_TRIES_PER_HOUR = 10

HELP = (
    "I'm <b>EMMA</b>, your property assistant.\n\n"
    "Just ask in plain words, e.g. <i>who owes rent?</i>, <i>report a repair</i>, <i>what jobs do I have?</i>\n\n"
    "/new  start a fresh conversation\n"
    "/whoami  which EMMA login this chat is linked to\n"
    "/unlink  disconnect this Telegram account"
)
NOT_LINKED = (
    "Hi! I'm <b>EMMA</b>. This Telegram account isn't linked to an EMMA login yet.\n\n"
    "1. Sign in on the EMMA website\n"
    "2. Open <b>Ask EMMA</b> and tap <b>Telegram</b>\n"
    "3. Tap <b>Open in Telegram</b> (or send me <code>/link CODE</code>)"
)


def to_telegram_html(text: str) -> str:
    """The chat's light markdown -> Telegram's small HTML subset."""
    out = []
    for line in (text or "").splitlines():
        if re.fullmatch(r"\s*\|?[\s:|-]*-{2,}[\s:|-]*", line):
            continue                                   # table separator
        if line.strip().startswith("|"):
            line = " · ".join(c.strip() for c in line.strip().strip("|").split("|"))
        line = re.sub(r"^(\s*)[-*]\s+", r"\1• ", line)
        line = re.sub(r"^#+\s*", "", line)
        line = html.escape(line, quote=False)
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"`([^`]+)`", r"<code>\1</code>", line)
        out.append(line)
    return "\n".join(out).strip() or "…"


def _field(k: str, v) -> str:
    if isinstance(v, (int, float)) and re.search(r"amount|rent|fee|deposit", k):
        v = f"${v:,.2f}"
    return f"{k.replace('_', ' ').capitalize()}: {v}"


class TelegramBot:
    def __init__(self, app, token: str):
        self.app = app
        self.api = f"https://api.telegram.org/bot{token}"
        self.history: dict[int, deque] = defaultdict(lambda: deque(maxlen=HISTORY))
        self.locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.pending: dict[str, dict] = {}          # short id -> proposed change
        self.link_tries: dict[int, deque] = defaultdict(deque)
        self.http = None

    # ---------------------------------------------------------- plumbing
    async def call(self, method: str, **params):
        r = await self.http.post(f"{self.api}/{method}", json=params)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"{method}: {data.get('description')}")
        return data["result"]

    async def say(self, chat_id: int, text: str, **extra):
        for i in range(0, len(text), 3900):          # Telegram's limit is 4096
            try:
                await self.call("sendMessage", chat_id=chat_id, text=text[i:i + 3900],
                                parse_mode="HTML", disable_web_page_preview=True, **extra)
            except RuntimeError:                      # bad HTML: send it plain
                await self.call("sendMessage", chat_id=chat_id, text=re.sub(r"<[^>]+>", "", text[i:i + 3900]), **extra)

    async def as_user(self, who: dict, method: str, path: str, body: dict) -> httpx.Response:
        """Call this API in-process as the linked person."""
        token = create_access_token(who["id"], who["company_id"], who["role"])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://emma.internal",
                                     headers={"Authorization": f"Bearer {token}"}, timeout=180) as c:
            return await c.request(method, path, json=body)

    async def run(self):
        self.http = httpx.AsyncClient(timeout=60)
        outbox = asyncio.create_task(self.outbox_loop())
        offset, backoff = None, 1
        while True:
            try:
                if not links.bot_state["username"]:
                    me = await self.call("getMe")
                    links.bot_state["username"] = me["username"]
                    await self.call("setMyCommands", commands=[
                        {"command": "new", "description": "Start a fresh conversation"},
                        {"command": "whoami", "description": "Which EMMA login this chat uses"},
                        {"command": "unlink", "description": "Disconnect this Telegram account"},
                        {"command": "help", "description": "What I can do"},
                    ])
                    log.warning("Telegram bot @%s is running", me["username"])
                updates = await self.call("getUpdates", offset=offset, timeout=50,
                                          allowed_updates=["message", "callback_query"])
                backoff = 1
                for u in updates:
                    offset = u["update_id"] + 1
                    asyncio.create_task(self.handle(u))
            except asyncio.CancelledError:
                outbox.cancel()
                await self.http.aclose()
                raise
            except Exception as e:  # network blips, Telegram hiccups, another poller
                log.warning("Telegram polling problem: %s", e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def handle(self, update: dict):
        try:
            if "callback_query" in update:
                await self.on_button(update["callback_query"])
            elif "message" in update:
                await self.on_message(update["message"])
        except Exception:
            log.exception("Telegram update failed")

    # ---------------------------------------------------------- messages
    async def on_message(self, msg: dict):
        chat, sender = msg.get("chat", {}), msg.get("from", {})
        if chat.get("type") != "private" or sender.get("is_bot"):
            return
        tg_id, chat_id = sender["id"], chat["id"]
        text = (msg.get("text") or "").strip()
        if not text:
            return await self.say(chat_id, "I can only read text messages for now.")

        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@")[0].lower()
        if cmd in ("/start", "/link"):
            if arg.strip():
                return await self.do_link(chat_id, sender, arg.strip())
            who = await run_in_threadpool(links.lookup, tg_id)
            return await self.say(chat_id, (f"You're linked as <b>{html.escape(who['username'])}</b>.\n\n" + HELP) if who else NOT_LINKED)
        if cmd == "/help":
            return await self.say(chat_id, HELP)
        if cmd == "/unlink":
            gone = await run_in_threadpool(links.unlink, tg_id)
            self.history.pop(tg_id, None)
            return await self.say(chat_id, "Unlinked. This Telegram account can no longer reach your EMMA data." if gone else "This Telegram account wasn't linked.")

        who = await run_in_threadpool(links.lookup, tg_id)
        if who is None:
            return await self.say(chat_id, NOT_LINKED)
        if cmd == "/whoami":
            return await self.say(chat_id, f"Linked to <b>{html.escape(who['username'])}</b> ({who['role'].replace('_', ' ')}).")
        if cmd == "/new":
            self.history.pop(tg_id, None)
            return await self.say(chat_id, "Fresh start. What can I help with?")
        if cmd.startswith("/"):
            return await self.say(chat_id, HELP)

        async with self.locks[tg_id]:
            hist = self.history[tg_id]
            hist.append({"role": "user", "content": text[:4000]})
            msgs = list(hist)
            while msgs and msgs[0]["role"] != "user":
                msgs.pop(0)
            await self.call("sendChatAction", chat_id=chat_id, action="typing")
            r = await self.as_user(who, "POST", "/chat", {"messages": msgs, "channel": "telegram"})
            if r.status_code != 200:
                hist.pop()
                try:
                    detail = r.json().get("detail")
                except ValueError:
                    detail = None
                return await self.say(chat_id, html.escape(str(detail or "Sorry, something went wrong. Please try again.")))
            data = r.json()
            hist.append({"role": "assistant", "content": data["reply"]})
            await self.say(chat_id, to_telegram_html(data["reply"]))
            for a in data.get("actions", []):
                await self.offer(chat_id, tg_id, a)

    async def offer(self, chat_id: int, tg_id: int, action: dict):
        now = time.time()
        for k in [k for k, p in self.pending.items() if p["exp"] < now]:
            del self.pending[k]
        key = secrets.token_urlsafe(9)
        self.pending[key] = {"token": action["token"], "tg": tg_id, "label": action["label"], "exp": now + ACTION_SECONDS}
        fields = [_field(k, v) for k, v in action["fields"].items() if not k.endswith("_id") and k != "id"]
        body = f"<b>{html.escape(action['label'])}</b>\n" + "\n".join(html.escape(f) for f in fields)
        await self.say(chat_id, body, reply_markup={"inline_keyboard": [[
            {"text": "✅ Confirm", "callback_data": f"ok:{key}"},
            {"text": "✖ Cancel", "callback_data": f"no:{key}"},
        ]]})

    # ---------------------------------------------------------- notifications
    async def outbox_loop(self):
        """Every few seconds, deliver new notifications (e.g. "New job") to
        people who've linked Telegram, with a Mark as read button."""
        while True:
            try:
                for n in await run_in_threadpool(notify.telegram_outbox):
                    chat_id = await run_in_threadpool(links.telegram_id_for_user, n["user_id"])
                    if chat_id is None:
                        await run_in_threadpool(notify.set_telegram_status, n["id"], "not_linked")
                        continue
                    icon = {"job_assigned": "🔔", "job_rescheduled": "📅", "job_reminder": "⏰"}.get(n["kind"], "🔔")
                    text = f"{icon} <b>{html.escape(n['title'])}</b>\n{html.escape(n['body'] or '')}"
                    markup = None if n["read"] else {"inline_keyboard": [[{"text": "✓ Mark as read", "callback_data": f"rd:{n['id']}"}]]}
                    try:
                        await self.call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                                        **({"reply_markup": markup} if markup else {}))
                        await run_in_threadpool(notify.set_telegram_status, n["id"], "sent")
                    except Exception as e:
                        log.warning("Telegram notification failed: %s", e)
                        await run_in_threadpool(notify.set_telegram_status, n["id"], "failed")
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Telegram outbox problem")
            await asyncio.sleep(5)

    async def on_read(self, cb: dict, notification_id: str):
        who = await run_in_threadpool(links.lookup, cb["from"]["id"])
        ok = who is not None and await run_in_threadpool(notify.mark_read_as, notification_id, who["id"])
        await self.call("answerCallbackQuery", callback_query_id=cb["id"], text="Marked as read" if ok else "Couldn't find that notification.")
        msg = cb.get("message") or {}
        if ok and msg:
            await self.call("editMessageReplyMarkup", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
                            reply_markup={"inline_keyboard": [[{"text": "✓ Read", "callback_data": "noop"}]]})

    async def on_button(self, cb: dict):
        tg_id = cb["from"]["id"]
        msg = cb.get("message") or {}
        verb, _, key = (cb.get("data") or "").partition(":")
        if verb == "rd":
            return await self.on_read(cb, key)
        if verb == "noop":
            return await self.call("answerCallbackQuery", callback_query_id=cb["id"])
        p = self.pending.get(key)
        if p is None or p["exp"] < time.time() or p["tg"] != tg_id:
            return await self.call("answerCallbackQuery", callback_query_id=cb["id"], text="This has expired. Ask EMMA again.")
        del self.pending[key]
        label = html.escape(p["label"])

        async def finish(line: str):
            await self.call("answerCallbackQuery", callback_query_id=cb["id"])
            if msg:
                await self.call("editMessageText", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
                                text=f"<b>{label}</b>\n{line}", parse_mode="HTML")

        if verb != "ok":
            self.history[tg_id].append({"role": "assistant", "content": f"[{p['label']}: the person cancelled it]"})
            return await finish("Cancelled.")
        who = await run_in_threadpool(links.lookup, tg_id)
        if who is None:
            return await finish("This Telegram account is no longer linked.")
        r = await self.as_user(who, "POST", "/chat/confirm", {"token": p["token"]})
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code == 200 and data.get("ok"):
            self.history[tg_id].append({"role": "assistant", "content": f"[{p['label']}: the person confirmed it and it was done]"})
            return await finish("✅ Done.")
        why = data.get("message") or data.get("detail") or "Something went wrong."
        self.history[tg_id].append({"role": "assistant", "content": f"[{p['label']}: failed: {why}]"})
        await finish(f"Couldn't do it: {html.escape(str(why))}")

    async def do_link(self, chat_id: int, sender: dict, code: str):
        tg_id = sender["id"]
        tries, now = self.link_tries[tg_id], time.time()
        while tries and now - tries[0] > 3600:
            tries.popleft()
        if len(tries) >= LINK_TRIES_PER_HOUR:
            return await self.say(chat_id, "Too many tries. Please wait an hour and get a new code from the website.")
        tries.append(now)
        user_id = links.take_code(code)
        if user_id is None:
            return await self.say(chat_id, "That code isn't valid or has expired. Get a new one on the website (Ask EMMA → Telegram).")
        await run_in_threadpool(links.link, tg_id, sender.get("username"), user_id)
        self.history.pop(tg_id, None)
        who = await run_in_threadpool(links.lookup, tg_id)
        name = html.escape(who["username"]) if who else "your account"
        await self.say(chat_id, f"✅ Linked to <b>{name}</b>. You can ask me anything now.\n\n" + HELP)


def start(app) -> "asyncio.Task | None":
    token = settings.telegram_bot_token.strip()
    if not token:
        return None
    if settings.telegram_bot_for.strip().lower() != settings.app_instance.strip().lower():
        log.warning("Telegram bot token set, but TELEGRAM_BOT_FOR=%s and this is APP_INSTANCE=%s: not starting it here.",
                    settings.telegram_bot_for, settings.app_instance)
        return None
    return asyncio.create_task(TelegramBot(app, token).run())
