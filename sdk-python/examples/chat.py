"""Example Latawiec app: a streaming chat on one live screen. Run:

    uv run uvicorn examples.chat:app --host 0.0.0.0 --port 8007

Streaming is refreshing fast: the handler appends to the conversation and
calls `app.refresh` per chunk, and every phone showing the screen watches
the reply grow. Swap `reply_to` for a real LLM call and this is a chatbot.
"""

import asyncio

import latawiec as lt

app = lt.Latawiec(dev=False, version="1")

messages: list[tuple[str, str]] = [("bot", "Hi! Say something.")]
_stream: asyncio.Task[None] | None = None


def reply_to(text: str) -> str:
    return f"You said “{text}” — a kite would put it better, but noted!"


def bubble(author: str, text: str) -> lt.Component:
    mine = author == "you"
    return lt.Text(
        text,
        color="#FFFFFF" if mine else "#1C2024",
        style=lt.Style(
            padding=12,
            margin=lt.Edges(top=8, left=48 if mine else 16, right=16 if mine else 48),
            background="#2962FF" if mine else "#ECEFF1",
            corner_radius=12,
            # New bubbles fade in on every live refresh instead of popping.
            appear=lt.Fade(250),
        ),
    )


@app.screen("home", live=True)
def home() -> lt.Component:
    return lt.Column(
        lt.Text("Kite chat", size=28, weight="bold", style=lt.Style(margin=48)),
        lt.Gallery(
            *[bubble(author, text) for author, text in messages],
            style=lt.Style(height="fill"),
        ),
        lt.TextInput("draft", hint="Message", style=lt.Style(margin=16)),
        lt.Button("Send", on_tap=lt.Submit("send", send=("draft",)), style=lt.Style(margin=16)),
    )


@app.action("send")
async def send(values: dict[str, str]) -> None:
    global _stream
    text = values.get("draft", "").strip()
    if not text:
        return
    messages.append(("you", text))
    app.refresh("home")

    async def stream() -> None:
        messages.append(("bot", ""))
        for word in reply_to(text).split(" "):
            grown = f"{messages[-1][1]} {word}".strip()
            messages[-1] = ("bot", grown)
            app.refresh("home")
            await asyncio.sleep(0.15)

    # Stream in the background so the tap answers immediately; a rapid
    # second send takes over the keyboard.
    if _stream is not None and not _stream.done():
        _stream.cancel()
    _stream = asyncio.get_running_loop().create_task(stream())
