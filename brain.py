"""The 'brain' -- answers any general question via Groq's fast cloud LLM, with
live tools (weather, web search, clock, reminders) so it can reach the real world.

The model can ask to run a tool; we execute it, feed the result back, and let the
model phrase the spoken answer. A rolling conversation gives short-term memory.
"""
import datetime
import json

import requests

import config
import tools

SYSTEM_INSTRUCTION = (
    f"You are {config.ASSISTANT_NAME}, a witty, capable voice assistant modeled "
    "on Tony Stark's AI. Your replies are spoken out loud, so keep them short, "
    "clear, and conversational -- usually one to three sentences. Never use "
    "markdown, bullet points, headings, code fences, or emoji; just speak plainly. "
    "Answer almost everything directly from your own knowledge. You have several "
    "tools, but use one ONLY when the user clearly and explicitly asks for that "
    "exact thing: call get_weather ONLY if they mention weather, temperature, "
    "rain, or forecast; call get_current_datetime ONLY if they ask the time or "
    "date; call web_search ONLY if they ask about news, current events, or to "
    "look something up. For reminders: call set_reminder when the user asks to "
    "be reminded of something AND gives a specific date and time -- convert any "
    "relative time (like 'tomorrow at 8pm' or 'in two hours') into an absolute "
    "ISO 8601 datetime using the current local time provided below; but if they "
    "ask for a reminder WITHOUT a clear date and time, do NOT guess -- ask them "
    "exactly when. Call list_reminders or cancel_reminder when they ask about or "
    "want to manage reminders. Call cancel_all_reminders when they ask to remove, "
    "clear, or delete ALL reminders at once. For anything else, do NOT call any tool -- just answer "
    "normally. Never default to the weather. If you can't tell what the user "
    "said or meant, briefly ask them to repeat instead of guessing. You may "
    "occasionally address the user as 'sir'."
)

_HTTP_TIMEOUT = 120
_MAX_TOOL_ROUNDS = 5


def _system_message():
    """The system prompt, refreshed with the current local time so the model can
    resolve relative reminder times into absolute datetimes."""
    now = datetime.datetime.now()
    return {"role": "system", "content": (
        SYSTEM_INSTRUCTION
        + f"\n\nThe current local date and time is {now:%A, %B %-d, %Y at %-I:%M %p} "
        + f"(ISO 8601: {now.isoformat(timespec='minutes')})."
    )}


def _http_post(url, payload, headers):
    resp = requests.post(url, json=payload, headers=headers, timeout=_HTTP_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code} {resp.text[:200]}")
    return resp.json()


def _parse_args(raw):
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {}


def _groq_chat(messages, tries=3):
    """POST a chat completion to Groq, retrying when the model emits a tool call
    Groq can't parse. llama-3.3-70b intermittently returns a 400 'tool_use_failed'
    (it formats a tool call wrong, e.g. as '<function=...>'); since generation is
    stochastic, simply re-rolling the request almost always succeeds."""
    payload = {"model": config.GROQ_MODEL, "messages": messages,
               "tools": tools.SCHEMAS, "tool_choice": "auto"}
    headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}"}
    for attempt in range(tries):
        try:
            return _http_post(
                "https://api.groq.com/openai/v1/chat/completions", payload, headers)
        except RuntimeError as exc:
            if "tool_use_failed" in str(exc) and attempt < tries - 1:
                continue
            raise


class Brain:
    """Groq's OpenAI-compatible cloud API, with tool-calling."""

    def __init__(self):
        self.provider = "groq"
        self.error = None
        self._messages = [_system_message()]
        if not config.GROQ_API_KEY:
            self.error = "no Groq API key is set (add it in Settings -- free at console.groq.com/keys)"

    @property
    def ready(self):
        return self.error is None

    def ask(self, question):
        if not self.ready:
            return f"I can't answer questions yet because {self.error}."
        tools.set_user_context(question)
        self._messages[0] = _system_message()  # refresh "current time" for reminders
        start = len(self._messages)
        self._messages.append({"role": "user", "content": question})
        try:
            for _ in range(_MAX_TOOL_ROUNDS):
                data = _groq_chat(self._messages)
                msg = data["choices"][0]["message"]
                self._messages.append(msg)
                calls = msg.get("tool_calls") or []
                if not calls:
                    return (msg.get("content") or "").strip() or "I'm not sure, sir."
                for call in calls:
                    fn = call.get("function", {})
                    result = tools.run(fn.get("name", ""), _parse_args(fn.get("arguments")))
                    self._messages.append({
                        "role": "tool", "tool_call_id": call.get("id", ""),
                        "name": fn.get("name", ""), "content": result,
                    })
            return "I got a little tangled up working that out, sir."
        except Exception as exc:
            del self._messages[start:]
            if "tool_use_failed" in str(exc):
                return "I had trouble with that one, sir -- could you say it again?"
            return f"I ran into a problem reaching my brain: {exc}"
