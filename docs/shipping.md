# Shipping a Latawiec app to the stores

The shells in this repo are the template: brand one with your identity and
point it at your production server, and it is your store app. Screens keep
living in Python — a store release is only needed when the shell itself
changes.

## Try it first, no Android toolchain

Every release on GitHub carries `latawiec-shell.apk`: a generic,
debug-signed shell with no server baked in. Install it on a phone or
emulator, start it, and it asks for your server's URL — pointed at
`uvicorn examples.hello:app --host 0.0.0.0`, your Python renders on the
phone five minutes after `pip install latawiec`. It is for trying things
out, not for stores: brand your own build below when it is time.

Before anything else, deploy your server with production settings:

```python
app = lt.Latawiec(dev=False, version="2026.11.07", login="signin")
```

`dev=False` makes the shells fetch over GET and cache screens on disk, and
the URL must be `https` — release builds refuse plain HTTP.

## Android (Play Console)

One-time: create an upload keystore and keep it out of git.

```sh
keytool -genkeypair -keystore upload.jks -alias upload -keyalg RSA \
    -validity 10000
```

Build a signed, branded bundle:

```sh
cd shell-android
./gradlew :app:bundleRelease \
    -PappId=com.example.kiteshop \
    -PappName="Kite Shop" \
    -PserverUrl=https://kites.example.com \
    -PversionName=1.0 -PversionCode=1 \
    -PreleaseStoreFile=/path/to/upload.jks \
    -PreleaseStorePassword=... -PreleaseKeyAlias=upload -PreleaseKeyPassword=...
```

Upload `app/build/outputs/bundle/release/app-release.aab` in Play Console.
The `ship-android` workflow does the same from the GitHub UI: add the
keystore (base64), its password, the alias, and the key password as the
`ANDROID_*` secrets, then run the workflow with your branding as inputs.

The template ships a kite launcher icon; swap in your brand by replacing
`app/src/main/res/mipmap-*/ic_launcher.png` (Android Studio's Image Asset
tool generates the densities).

## iOS (App Store Connect)

The production URL is baked at build time through the `LATAWIEC_SERVER_URL`
build setting; the bundle id, display name, and team ride on the same
command line:

```sh
cd shell-ios
xcodegen generate
xcodebuild archive \
    -project LatawiecShell.xcodeproj -scheme LatawiecShell \
    -archivePath build/KiteShop.xcarchive \
    LATAWIEC_SERVER_URL=https://kites.example.com \
    PRODUCT_BUNDLE_IDENTIFIER=com.example.kiteshop \
    INFOPLIST_KEY_CFBundleDisplayName="Kite Shop" \
    DEVELOPMENT_TEAM=YOURTEAMID
xcodebuild -exportArchive -archivePath build/KiteShop.xcarchive \
    -exportPath build -exportOptionsPlist ExportOptions.plist
```

with the usual `ExportOptions.plist` (`method: app-store-connect`), then
upload the `.ipa` with Transporter or `xcrun altool`. Signing uses your
Apple Developer account's automatic signing.

The template ships a kite app icon; swap in your brand by replacing
`Assets.xcassets/AppIcon.appiconset/icon.png` (a single 1024×1024 PNG).

The `ship-ios` workflow does all of the above from the GitHub UI: add the
distribution certificate (base64 `.p12` + its password), an App Store
provisioning profile (base64), and your team id as the `IOS_*` /
`APPLE_TEAM_ID` secrets, then run the workflow with your branding as
inputs and download the `.ipa` artifact for Transporter.

## Getting through app review

Both stores have a rule against an app downloading code, and an app whose
screens arrive over HTTP invites the question. Apple's guideline 2.5.2
says an app may not "download, install, or execute code which introduces
or changes features or functionality". Google Play's Device and Network
Abuse policy forbids downloading executable code — "dex, JAR, `.so`
files" — from any source but Play, and exempts "code that runs in a
virtual machine or an interpreter where either provides indirect access to
Android APIs".

What crosses the wire here is a DivKit card: JSON naming view types and
their properties. Every view class, gesture, animation and action the app
can perform is compiled into the binary the reviewer approved; the JSON
picks among them and fills in the text, the colors and the sizes. No dex,
no JAR and no shared object is fetched.

DivKit expressions — `Text("Hello, @{name}!")` — *are* evaluated, by an
interpreter inside DivKit: `div-evaluable` ships a tokenizer, a parser, an
evaluator and 316 class files in its `function` package. That is narrower
than the webview JavaScript Play's exemption was written for, which is the
useful thing to be able to say about it, and it is checkable in an
afternoon:

- Those functions are typed getters, arithmetic, string, date and color
  operations, and reads of a stored-value store.
- Nothing in the jar loads code or reflects: no `android/*` reference, no
  `ClassLoader`, no `java.lang.reflect`.
- Nothing in it opens a socket or a file either: no `openConnection`, no
  `openStream`, no `Socket`, no stream type. `java.net.URL` appears once
  in the whole jar, in the `Url` type, which constructs one to find out
  whether a string parses; `URLEncoder`/`URLDecoder` back `encodeUri()`
  and `decodeUri()`.
- Three things it does reach, which a paragraph that hid them would be
  worth nothing: `nowLocal()` reads the device clock and timezone
  (`System.currentTimeMillis`, `TimeZone.getDefault`), the date and number
  formatters read the default locale, and on iOS the stored-value store is
  on by default and file-backed (`divkit.values_storage`), so a card can
  write a value with `setStoredValue` that a later card reads back. The
  Android shell registers no storage, so there the same read falls back to
  its default — an asymmetry to know about before you rely on either
  behaviour.

So a card can compute a label and, on iOS, remember a flag. It cannot
reach the Android or iOS SDK, and the screens are a remote config in the
shape of a feed. That is the argument to make; neither store's text
mentions server-driven UI by name, and this repo has no app in production
yet to argue from. It answers 2.5.2 and no more. The rules a server-driven
app actually trips over are these:

- **Keep the server serving while the build is in review.** Guideline
  2.3.1(a) wants every new feature described in the Notes for Review *and
  accessible for review*. A reviewer who meets a login wall, an empty tab
  or a 502 files a rejection there is no arguing with. Put demo
  credentials in App Store Connect and Play Console whenever you set
  `login=`, and do not deploy a breaking change to the screens while a
  build is under review — the binary is frozen, your screens are not.
- **Never hold a feature back until approval.** Guideline 2.5.19 forbids
  hidden, dormant and undocumented features. A build whose server grows a
  tab the reviewer never saw is the one use of server-driven UI both
  stores treat as cheating, and 2.3.1(b) answers repeat offenders by
  closing the developer account rather than the build.
- **Write down that the screens come from your server.** In the Notes for
  Review it reads as an architecture. Found by a reviewer who was not
  told, it reads as something you hid.
- **Sell digital goods with `Purchase`.** Apple's 3.1.1 requires in-app
  purchase to unlock anything inside the app, and a screen your server
  renders is inside the app, so a `Button(on_tap=OpenUrl(...))` pointing
  at your own checkout is a rejection. The exception, in 3.1.1(a), is the
  US storefront, plus specific regions where Apple grants an entitlement
  (External Purchase Link, Music Streaming) — an application, not a
  default. See [In-app purchases](#in-app-purchases).

Changing copy, prices, layout or adding a screen needs no new review —
that is the whole point of the framework. A store release is needed when
the shell changes. What survives neither store is the app's purpose
changing after approval: a kite shop that becomes a casino is removed
whether the casino arrived in an update or over a socket.

## Deploying live screens

A live screen holds a WebSocket, and that socket belongs to the process
that accepted it. `app.refresh("chat")` walks the subscribers *that
process* knows about, so a second instance — `uvicorn --workers 4`, three
replicas, two machines — serves phones that the refresh never reaches.
Nothing errors and nothing is logged; those phones simply keep the render
they had until they reconnect.

The same is true of everything else your app keeps in memory. All the
examples here hold state in module globals, and so a `POST /actions/...`
that mutates one lands on a single instance: the next GET served by
another one answers from its own copy. Reassigning `app.tabs` or
`app.theme` at runtime moves one instance's manifest, and the shells key
their screen cache on that manifest's fingerprint.

**One instance is the simple answer**, and often the right one — but it is
one CPU core, so size it: a push renders once per subscriber and re-checks
that subscriber's access, and a 30-row screen costs about 3 ms of CPU to
render. Two hundred phones on one refresh is roughly 0.6 s of serialized
work, sent one socket at a time. The budget is subscribers × refresh rate
× render cost; measure it against what you actually push.

**To run more than one instance**, have whatever changes the data publish
to Redis pub/sub or Postgres `LISTEN/NOTIFY`, and have every instance
subscribe and refresh when it hears. Three things make or break that:

- Publish the **template**, not the path. `_subscribers` is keyed by the
  name you registered, so `app.refresh("chat/{room}")` is right and
  `app.refresh("chat/42")` raises `KeyError`. A refresh therefore pushes
  to every room's subscribers in that instance, each rendered for its own
  params — correct, but not a way to target one room.
- Wrap the call in `try/except KeyError`. An instance running older code
  does not know a newly added screen, and in the usual
  `pubsub.run_in_thread` shape one raise kills the listener thread — after
  which that instance honours no refreshes at all, which is a worse
  version of the problem this section is about.
- Refresh on hearing the message, not in the handler as well. An instance
  that both publishes and listens would otherwise render twice.

An instance with nobody subscribed to that screen does the work of an
empty loop, so publishing to all of them is fine.

**When an instance restarts**, every socket on it drops at once and both
shells reconnect on their own, backing off from one second to thirty; the
first message on a new socket is a full render, so a phone recovers its
current state by itself and may land on a different instance. That also
means the fan-out gap above heals at every reconnect. What does not
recover is anything pushed while a phone was away: a push is
fire-and-forget, with no queue, ack or replay, so `refresh` delivers
"here is the current state", never a stream of events you can count on.

## Deep links

Both shells open screens from URLs. A custom scheme works out of the box:
`latawiec://product/42` launches the app and opens the screen `product/42`
(the screen path starts at the URL's host). A link to a tab's root screen
selects that tab; any other screen is pushed onto the current stack.

Brand the scheme with the other identity flags: `-PdeepLinkScheme=kiteshop`
on Android, `LATAWIEC_URL_SCHEME=kiteshop` on the iOS command line.

Custom schemes are first-come-first-served on both OSes — any installed app
can claim `kiteshop://` — so links that carry anything sensitive should be
real `https://` links. For those (App Links / Universal Links, where the
screen is the URL path), both platforms require proof that you own the
domain:

Latawiec serves both ownership files itself — declare the apps and the
`/.well-known` endpoints appear on your server:

```python
app = lt.Latawiec(app_links=lt.AppLinks(
    android_package="com.example.kiteshop",
    android_fingerprints=("AA:BB:...",),   # keytool -printcert -jarfile app.apk
    ios_app_id="TEAMID.com.example.kiteshop",
))
```

What remains is per shell:

- **Android**: add a second `VIEW` intent-filter with
  `android:autoVerify="true"`, `android:scheme="https"` and your
  `android:host` to the activity in `app/src/main/AndroidManifest.xml`.
- **iOS**: add the Associated Domains entitlement
  (`applinks:yourdomain`) to the target. The shell already handles the
  incoming link.

## Push notifications

Register a device hook and push turns on — the shells see `"push": true`
in the manifest, ask the user for permission, and POST the platform's
token to your server:

```python
@app.device
def device(token: str, ctx: lt.Context) -> None:
    store(token, platform=ctx.platform, user=ctx.user)
```

The hook gets repeats (tokens rotate; shells re-register on boot), so
store idempotently. Registration is public by design — devices exist
before anyone signs in — and `ctx.user` is set once a bearer token rides
along.

Sending stays on your side, with your credentials. Put the target screen
under the `screen` key of the message's data and the tap opens it like a
deep link:

- **Android (FCM)**: create a Firebase project, add an Android app with
  your `applicationId`, and pass its three values at build time:
  `-PfirebaseProjectId=... -PfirebaseAppId=1:...:android:...
  -PfirebaseApiKey=...` (from the project's `google-services.json`:
  `project_id`, `mobilesdk_app_id`, `current_key`). A build without them
  runs push-free. Send via the FCM HTTP v1 API:

  ```json
  {"message": {"token": "<device token>",
    "notification": {"title": "Order shipped", "body": "Tap to track it"},
    "data": {"screen": "order/42"}}}
  ```

- **iOS (APNs)**: enable the Push Notifications capability for your App ID
  and add `CODE_SIGN_ENTITLEMENTS="$PWD/Push.entitlements"` to the
  `xcodebuild` command line (the file ships in `shell-ios/`; the default
  build omits it so free-team signing keeps working — give the flag an
  absolute path, or Xcode resolves it inside each Swift package too). Send
  with your APNs key:

  ```json
  {"aps": {"alert": {"title": "Order shipped", "body": "Tap to track it"}},
   "screen": "order/42"}
  ```

The foreground case matches the background one on both platforms: iOS
shows the banner, the Android shell re-posts the message as a local
notification (swap its placeholder icon together with the launcher one).

## Tablets and rotation

Both shells run on tablets and in landscape with nothing to configure:
the iOS target covers iPhone and iPad, and the Android activity handles
its own configuration changes, so turning the device keeps the screen
the user was on along with everything typed into it. The screens
themselves are yours — DivKit lays out whatever width it is given, so a
`Row` of cards that suits a phone will stretch on an iPad unless the
screen builder says otherwise (`ctx` carries no width today; branch on
what you do know, or design for both).

## In-app purchases

`Purchase("pro.month", "grant")` runs the platform's own buy flow and
submits your action with the store's receipt. **Verify that receipt with
Apple or Google in the handler before granting anything** — the shell
reports what the store told it, and a patched client can report whatever
it likes.

iOS needs no flag; StoreKit is part of the system. Android's billing
library costs about 81 KiB, most of what the budget has left, so an app
that sells nothing should not carry it:

```
./gradlew :app:assembleRelease -PwithBilling
```

That build measures 2,984,464 B against the default 2,901,528 B — still
inside the 3 MB budget. A default build says "This app was not built to
take payments" rather than leaving a silent button.

What remains is yours either way: a product with a matching id in App
Store Connect and in Play Console, and a server that checks the receipt.
To exercise a purchase on iOS without App Store Connect, point the
scheme's StoreKit configuration at `shell-ios/Latawiec.storekit`; the
shell's own tests do it with `SKTestSession`.

## Video beyond the platform player

The default shell plays video through Android's own `MediaPlayer` and
iOS's `AVPlayer`: MP4 and HLS, which covers most apps and costs nothing.
DASH and adaptive HLS need ExoPlayer, which with those two formats costs
about 726 KiB — more than the whole 3 MB budget has left — so it is a
per-build choice:

```
./gradlew :app:assembleRelease -PwithVideo
```

That build measures 3,644,695 B against the default 2,901,528 B, which
is deliberately over the budget CI enforces for the clean shell. iOS
needs no flag: AVPlayer already plays what it plays, and nothing larger
ships with the shell.

## Location, the camera and Face ID

None needs a build flag, but iOS shows your own sentence in the system
prompt and App Store review rejects a vague one. (The Face ID string is
shown once, when the app first uses it; the sentence on each `Unlock` is
that action's own `reason`.) Pass them with the
`locationReason`, `cameraReason` and `faceIdReason` inputs of
`ship-ios`, or as `LATAWIEC_LOCATION_REASON="Finds shops near you."`,
`LATAWIEC_CAMERA_REASON="Adds a photo to your report."` and
`LATAWIEC_FACEID_REASON="Confirms a payment is yours."` on the
`xcodebuild` command line. An app that never asks for a location can
delete the two `ACCESS_*_LOCATION` lines from
`app/src/main/AndroidManifest.xml`; the camera needs no Android
permission at all, since the system camera app takes the shot. `Unlock`
uses `USE_BIOMETRIC`, which is granted at install with no prompt; an app
without `Unlock` can delete that line too.

The iOS simulator has no camera (it claims otherwise, then shows a blank
capture screen), so the shell treats it as camera-less: `source="camera"`
says so there, and taking a shot needs a real device. The Android
emulator does have one.

## The DivKit dependency

Someone's legal department will ask about this, so here are the facts in a
form they can check themselves.

DivKit is Apache-2.0, `Copyright 2022 YANDEX LLC`, developed in the open
at [github.com/divkit/divkit](https://github.com/divkit/divkit). The
Android shell pins `com.yandex.div:div:33.10.0` and
`com.yandex.div:coil:33.10.0` from Maven Central, the iOS shell pins
`divkit-ios` 33.10.0 through SPM as an `exactVersion`.

Apache-2.0 asks you to keep the license text with the app, and the
acknowledgements screen is the usual place. There is no file named NOTICE,
but do not copy the Apache header alone: `divkit-ios`'s single `LICENSE`
runs 406 lines, because after Apache-2.0 it carries notices for what
DivKit itself builds on — four MIT grants and the JSON License, whose "The
Software shall be used for Good, not Evil" clause is the line corporate
legal refuses on sight. Before you reproduce that list, check what your
app actually links: `org.json`, for one, is not in the Android release
dependency tree at all (the platform provides it). The Android AARs carry
no license file of their own, so take the text from the repository.

The license is rarely the real question. The real one is whether the app
talks to Yandex, and it does not — no Yandex host appears anywhere in the
default release build, dex, resources and assets alike:

```sh
cd shell-android
unzip -oq app/build/outputs/apk/release/app-release-unsigned.apk -d /tmp/apk
grep -raoiE '[a-z0-9.-]*(yandex|metrica)[a-z0-9.-]*\.(ru|net|com|tech)' /tmp/apk
```

Unzip first and grep the 616 extracted entries: the APK's own entries are
deflated, so running `strings` on the `.apk` file reads none of the dex and
tells you nothing. (A `grep -ac 'com/yandex/div/core' /tmp/apk/classes.dex`
is the check that your check works — keep the `-a`, or a grep that treats
the dex as binary answers nothing at all.)

The `yandex` strings that *are* in there are class names
(`com/yandex/div/core/...`) and animation property keys
(`yandex:fade:alpha`). At runtime the app talks to three parties — your
server, Firebase, and the map's tile host:

- the `-PserverUrl` you built with (`http://10.0.2.2:8000` if you passed none)
- `fcmregistrations.googleapis.com` and `firebaseinstallations.googleapis.com`,
  Firebase for push, in your own project
- `tile.openstreetmap.org`, the `Map` fallback

Grepping the same files for URLs prints twenty-eight distinct strings:

```sh
grep -raoE 'https?://[a-zA-Z0-9._/{}:-]+' /tmp/apk | sed 's|^[^:]*:||' | sort -u
```

Five of those are the destinations above. None of the other twenty-three
is an endpoint — among them XML and SVG namespace URIs, the
`https://your-server.example.com` placeholder from the shell's own URL
field, license and upstream-source links (`apache.org`, `mozilla.org`,
`android.googlesource.com`), OkHttp's public-suffix sources, DivKit's
hot-reload README, and bug-tracker links left in library comments. Read
what you find; a URL in a binary is not a request.

DivKit's `beacon` module does make requests — `SendBeaconManager` keeps a
SQLite queue and POSTs log URLs — and `div-histogram` collects render
timings. Both arrive transitively, both are for a host app that opts in,
and the release build does not have them: R8 drops them when nothing
references them, and `classes.dex` contains no `SendBeacon` class at all —
`grep -ac SendBeacon /tmp/apk/classes.dex` answers `0`. All that is left of
histogram is the `HistogramFilter` type and a `getHistogramReporter`
accessor. Grep case-insensitively for `beacon` and you get three hits, all
of them the bare strings `TAP_BEACONS_ENABLED`,
`VISIBILITY_BEACONS_ENABLED` and `SWIPE_OUT_BEACONS_ENABLED` — names of an
experiment enum whose class and whose readers R8 removed. On iOS the
question does not arise: `divkit-ios` ships neither module.

What leaves the device at runtime is therefore screen requests to your
server, an FCM token if you use push, and map tiles. That last one hands a
third party a viewport — roughly where the user is looking — so point
`Map(tiles=...)` at your own tile server for anything real; it is the
private choice and also the one OpenStreetMap's tile usage policy asks of
you.

If your organisation rules out dependencies of Russian origin whatever
their license and traffic — some do — then this framework is not an
option for you today. The DSL emits DivKit JSON and both shells are
DivKit renderers; swapping the renderer is not a build flag.

## What a release pins

- The shell version (`versionCode`/`CFBundleVersion`) — bump per upload
- The production server URL — screens, tabs, auth, and cache policy stay
  server-side and change without a store release
- The CI size budget keeps the Android release near native weight
