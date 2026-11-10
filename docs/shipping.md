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

That build measures 3,644,695 B against the default 2,901,512 B, which
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

## What a release pins

- The shell version (`versionCode`/`CFBundleVersion`) — bump per upload
- The production server URL — screens, tabs, auth, and cache policy stay
  server-side and change without a store release
- The CI size budget keeps the Android release near native weight
