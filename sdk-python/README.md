# latawiec

Native mobile apps flown from a Python backend — server-driven UI on
[DivKit](https://divkit.tech).

```python
import latawiec as lt

app = lt.Latawiec()


@app.screen("home")
def home() -> lt.Component:
    return lt.Column(
        lt.Text("Hello from the server", size=24),
        lt.Button("Open checkout", on_tap=lt.Navigate("checkout")),
    )
```

`app` is a regular ASGI/FastAPI app; `uvicorn main:app` serves the rendered DivKit card
JSON at `/screens/home`, ready for a native shell to render.

Early development. See the [repository](https://github.com/krszozda/latawiec) for the
full picture: the native shells, state, and hot reload are planned but not built yet.
