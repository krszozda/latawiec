# Shipping a Latawiec app to the stores

The shells in this repo are the template: brand one with your identity and
point it at your production server, and it is your store app. Screens keep
living in Python — a store release is only needed when the shell itself
changes.

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

The template ships no launcher icon. Add yours as
`app/src/main/res/mipmap-*/ic_launcher.png` (Android Studio's Image Asset
tool generates the densities) and declare it on the `<application>` element
in `app/src/main/AndroidManifest.xml`:

```xml
android:icon="@mipmap/ic_launcher"
```

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

The template ships no app icon. Create `Assets.xcassets` with an `AppIcon`
set, list it in `project.yml` next to the sources
(`sources: [Sources, Assets.xcassets]`) and add
`ASSETCATALOG_COMPILER_APPICON_NAME: AppIcon` to the target's settings,
then regenerate with `xcodegen generate`.

## What a release pins

- The shell version (`versionCode`/`CFBundleVersion`) — bump per upload
- The production server URL — screens, tabs, auth, and cache policy stay
  server-side and change without a store release
- The CI size budget keeps the Android release near native weight
