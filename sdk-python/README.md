# latawiec

Native mobile apps flown from a Python backend — server-driven UI on
[DivKit](https://divkit.tech).

```python
import latawiec as lt

screen = lt.Column(
    lt.Text("Hello from the server", size=24),
)
payload = lt.render(screen)  # DivKit card JSON, ready for a native shell to render
```

Early development. See the [repository](https://github.com/krszozda/latawiec) for the
full picture: native shells, actions, navigation, and hot reload are planned but not
built yet.
