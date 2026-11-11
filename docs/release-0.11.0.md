The app release: twelve PRs that take Latawiec from "runs an app" to "runs the app you were going to write anyway".

Install `latawiec-shell.apk` below, type your server's address, and everything here arrives over HTTP.

## One break, on purpose

- **Text is text** (#71): every string a component takes is now shown exactly as written, `@{...}` included. Until now anything you rendered was a DivKit expression first — so a product name, a review or a chat message someone else typed could read a screen variable, or quietly render as nothing. Ask for an expression where you mean one: `Text(Expression("Hello, @{name}!"))`. If your app interpolates a variable into text, that is one wrapper per call and nothing else.

  The same fix ends a bug worth knowing about: a backslash is an escape inside a DivKit expression, so `Text("Saved to C:\\reports")` rendered as an empty line on Android. Both characters now travel as expressions that evaluate to themselves, which is the only form that reads back exactly on both platforms — pinned in CI against DivKit's own evaluator, and on a device and a simulator by hand.

## See all of it at once

- **An example that shows the framework off** (#64): `examples/showcase.py` walks through the components, what a tap can do, live screens and pagination, the device and the store, with each screen saying what it demonstrates. One readable file, and the fastest way to learn what this does. Its own tests keep it from rotting — including one that fails if a feature stops being shown.

## What the user sees

- **Animations in `Style`** (#54): `appear=Fade() / Slide() / Grow()`, `disappear`, and `move=N` for layout shifts. They fire on live refreshes too, so streamed content glides in instead of popping.
- **Feed mechanics** (#56): `refreshable=True` gives a screen the platform's own pull-to-refresh; a `LoadMore("page")` sentinel at the end of a `Gallery` turns a live screen into an infinite scroll.
- **Maps** (#60): `Map(52.2297, 21.0122, markers=(Marker(...),))` pans and zooms natively — MapKit on iOS, a tile view the shell paints on Android. No SDK, no API key, 9 KB of dex and nothing in the APK. `tiles=` points both shells at your own raster server.
- **Phones and tablets** (#62): iPhone, iPad and both orientations. Turning the phone keeps the screen you were on along with everything typed into it, and the stack comes back by name after Android reclaims the process.
- **The chrome changes mid-session** (#53): add a tab in Python and it appears on phones already running, without a restart — the manifest's fingerprint rides every screen response.

## What the device can be asked for

Each of these raises the system's own prompt, on a control the user pressed on purpose, and none costs the clean build a dependency:

- **Photos** (#55, #58): `ImagePicker("photo")` opens the gallery, `source="camera"` the camera; both ship the result to `@app.upload` and preview whatever URL it returns. The camera needs no Android permission — the system camera app takes the shot — and costs 564 bytes.
- **Location** (#57): `RequestLocation("spot", then="search")` puts `"lat,lon"` in a screen variable and submits your action with it. 48 bytes, and no Play Services: Android asks every enabled provider and takes the first fix, because GPS never arrives indoors.
- **Biometrics** (#59): `Unlock("pay", send=("amount",))` asks for the fingerprint, the face or the passcode and submits only once it passes. 44 bytes. It gates the tap, not the server — the docs say so in three places.
- **In-app purchases** (#63): `Purchase("pro.month", "grant")` runs the store's flow and submits the receipt for your server to verify. The product id deliberately does not travel in the request; a handler reads it out of the verified receipt. StoreKit needs no flag, Play Billing ships behind `-PwithBilling` (81 KiB, still inside the budget).
- **Video beyond the platform player** (#61): DASH and adaptive HLS behind `-PwithVideo` (726 KiB, deliberately over the budget the clean shell keeps).

## Bugs this release found by running things

The reviews on these PRs were aimed at what costs a user something, and several found it:

- A purchase was finished before the server had its receipt, and neither shell listened for a purchase approved later or made on another device — a customer could be charged and get nothing. Purchases now settle only after your handler answers, and both shells take deliveries nobody tapped for.
- Rotating the phone threw the user back to the tab root, taking everything typed with it.
- A `RequestLocation` whose prompt outlived its activity left every location provider running for the rest of the session.
- `Video` rendered zero pixels tall: DivKit sizes an element to its content and a video has no size until it loads.
- On iPad, `Share` was a dead button — UIKit refuses a popover with nothing to point at.
- `SetVariable` never declared the variable it writes into, so DivKit dropped the write and every expression reading it rendered empty.

Release APK: 2,901,528 B, still under the 3 MB CI budget. Opt-in builds measure 2,984,464 B with billing and 3,644,695 B with ExoPlayer.
