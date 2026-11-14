import AVFoundation
import CoreLocation
import DivKit
import LocalAuthentication
import PhotosUI
import UIKit
import UniformTypeIdentifiers
import os

private let log = Logger(subsystem: "io.github.krszozda.latawiec", category: "shell")

/// The server's WebSocket close code for a missing or rejected token.
private let notAuthorized = 4401

/// How long a RequestLocation waits for a fix before giving up on one.
private let fixTimeout: TimeInterval = 10

/// How often a held-open socket proves it is still there. A ping gets the
/// same span again to be answered before the socket counts as gone.
private let socketPingInterval: TimeInterval = 20

/// Both shells word it the same way, so the docs can promise it.
private let noLock = "This device has no lock set up"

/// What a tap on an ImagePicker(source="camera") can do.
enum CameraGate {
    case ready
    /// Access was turned off in Settings; only the user can undo that.
    case accessOff
    case missing
}

/// Both ways the camera can be unusable end in a sentence rather than in
/// the blank capture screen UIKit otherwise presents. `.notDetermined` is
/// ready on purpose: the picker raises the system prompt itself, which is
/// the one tap the user expects.
func cameraGate(status: AVAuthorizationStatus, hasCamera: Bool) -> CameraGate {
    switch status {
    case .denied, .restricted:
        return .accessOff
    default:
        return hasCamera ? .ready : .missing
    }
}

/// One Latawiec screen: a DivView fed over a WebSocket.
///
/// The server sends the card on connect and holds the socket; when it restarts
/// (`uvicorn --reload` on every code change) the socket drops and the reconnect
/// delivers the fresh screen — that is the live-reload loop. Every screen on
/// the navigation stack keeps its own socket, so all of them come back fresh.
final class ScreenViewController: UIViewController {
    let screen: String

    private lazy var components = DivKitComponents(
        // LoadMore rides a visibility action; without this flag DivKit
        // swallows its URL instead of handing it to the handler below.
        divCustomBlockFactory: MapBlockFactory(),
        flagsInfo: DivFlagsInfo(useUrlHandlerForVisibilityActions: true),
        urlHandler: DivUrlHandlerDelegate { [weak self] url in self?.handle(url) }
    )
    private lazy var divView = DivView(divKitComponents: components)
    private let spinner = UIActivityIndicatorView(style: .large)
    private var socket: URLSessionWebSocketTask?
    private var reconnectDelay: TimeInterval = 1

    /// Poll interval of a refresh=N screen, from its response header.
    private var pollSeconds: TimeInterval?
    private var appeared = false

    /// Which screen variable the in-flight photo pick belongs to.
    private var pendingPickVariable: String?

    /// A RequestLocation waiting on the permission prompt or on a fix.
    private struct LocationAsk {
        let variable: String
        let action: String?
    }

    private var pendingLocation: LocationAsk?
    private var unlockContext: LAContext?
    private var purchaseWatcher: Task<Void, Never>?

    /// Handler of the latest buy tap.
    private var purchaseAction: String?

    /// Variables the shell wrote itself — a picked photo, a location fix.
    /// A re-render resets the card's data and would drop them, so they are
    /// kept here and written back after every render, which is also how the
    /// Android shell behaves (its setData keeps the variables alive).
    private var ownVariables: [String: String] = [:]

    /// Bumped per ask, so a late timeout cannot answer a newer one.
    private var locationAsks = 0
    private lazy var locations: CLLocationManager = {
        let manager = CLLocationManager()
        manager.delegate = self
        return manager
    }()

    private lazy var refresher = makeRefresher()
    private var wantsRefresher = false

    init(screen: String) {
        self.screen = screen
        super.init(nibName: nil, bundle: nil)
        // A screen name is a route, not a title ("product/42"): pushed
        // screens show a bare back chevron and the app draws its own header.
        navigationItem.backButtonDisplayMode = .minimal
    }

    override var preferredStatusBarStyle: UIStatusBarStyle {
        Chrome.statusBarStyle(over: Chrome.background)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }

    deinit {
        purchaseWatcher?.cancel()
        socket?.cancel()
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = Chrome.screenBackground
        view.addSubview(divView)
        divView.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            divView.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            divView.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor),
            divView.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor),
            divView.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor),
        ])
        view.addSubview(spinner)
        spinner.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            spinner.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            spinner.centerYAnchor.constraint(equalTo: view.centerYAnchor),
        ])
        spinner.startAnimating()
        if Server.dev {
            connect()
        } else {
            fetchScreen()
        }
    }

    /// The user acted and nothing happened; say so instead of only logging.
    private func showError(_ message: String) {
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        present(alert, animated: true)
    }

    private func retryFetch() {
        let delay = reconnectDelay
        reconnectDelay = min(delay * 2, 30)
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
            self?.fetchScreen()
        }
    }

    /// Production path: render the last-known screen from disk right away,
    /// then revalidate over GET and swap in the fresh payload — unless the
    /// cached copy is "static", which lives until the manifest version moves.
    private func fetchScreen() {
        // A response that outlives a sign-out wipe must not store.
        let asOf = ScreenCache.shared.generation
        // Mid-pull the content is already on screen: rendering the cached
        // copy would snap the indicator shut within a frame.
        let cached = refresher.isRefreshing ? nil : ScreenCache.shared.load(screen)
        if let cached {
            show(data: cached.payload)
            if cached.policy == "static" { return }
            // A cached live screen subscribes straight away — the socket's
            // backoff covers an unreachable server, and its first message
            // is the fresh render.
            if cached.policy == "live" {
                DispatchQueue.main.async { self.connect() }
                return
            }
            // The interval from the cache keeps a polled screen's rhythm
            // even when the revalidation fetch fails.
            if cached.policy.hasPrefix("poll:") {
                pollSeconds = TimeInterval(cached.policy.dropFirst("poll:".count))
            }
        }
        let path = screen.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? screen
        guard let url = URL(string: "\(Server.url)/screens/\(path)") else { return }
        var request = URLRequest(url: url)
        // URLSession heuristically caches 200s that carry no Cache-Control,
        // which would serve a stale screen instead of hitting the server;
        // freshness is ScreenCache's job.
        request.cachePolicy = .reloadIgnoringLocalCacheData
        Auth.authorize(&request)
        let hadCache = cached != nil
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            guard let self else { return }
            if let error {
                // With a cached copy on screen this is offline mode; a blank
                // screen keeps retrying on the socket's backoff, and a polled
                // screen keeps its rhythm.
                log.warning("screen \(self.screen) fetch failed: \(String(describing: error))")
                DispatchQueue.main.async {
                    self.settleRefresher()
                    if hadCache { self.schedulePoll() } else { self.retryFetch() }
                }
                return
            }
            let status = (response as? HTTPURLResponse)?.statusCode ?? -1
            if status == 401 {
                DispatchQueue.main.async { Auth.unauthorized() }
                return
            }
            guard status == 200, let data else {
                log.warning("screen \(self.screen) answered HTTP \(status)")
                DispatchQueue.main.async {
                    self.settleRefresher()
                    if hadCache { self.schedulePoll() } else { self.retryFetch() }
                }
                return
            }
            self.reconnectDelay = 1
            let http = response as? HTTPURLResponse
            let header = http?.value(forHTTPHeaderField: "Cache-Control") ?? ""
            let live = http?.value(forHTTPHeaderField: "X-Latawiec-Live") != nil
            let refresh = http?.value(forHTTPHeaderField: "X-Latawiec-Refresh")
            let policy = header.contains("no-store") ? "no-store"
                : header.contains("immutable") ? "static"
                : live ? "live"
                : refresh.map { "poll:\($0)" } ?? "swr"
            if policy != "no-store" {
                ScreenCache.shared.store(self.screen, policy: policy, payload: data, asOf: asOf)
            }
            let refreshable = http?.value(forHTTPHeaderField: "X-Latawiec-Refreshable") != nil
            DispatchQueue.main.async {
                if refreshable { self.wantsRefresher = true }
                self.show(data: data)
            }
            if let fingerprint = http?.value(forHTTPHeaderField: "X-Latawiec-Manifest") {
                // The chrome changed server-side (a tab appeared?).
                DispatchQueue.main.async {
                    (UIApplication.shared.delegate as? AppDelegate)?
                        .manifestChanged(to: fingerprint)
                }
            }
            if live {
                // A live screen subscribes after its first render; every
                // app.refresh() lands here.
                DispatchQueue.main.async { self.connect() }
            } else {
                DispatchQueue.main.async {
                    self.pollSeconds = refresh.flatMap(TimeInterval.init)
                    self.schedulePoll()
                }
            }
        }.resume()
    }

    /// A covered polled screen stops ticking; coming back refetches now.
    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        if appeared, pollSeconds != nil { fetchScreen() }
        appeared = true
    }

    /// Polled screens refetch on their interval while on display.
    private func schedulePoll() {
        guard let seconds = pollSeconds else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds) { [weak self] in
            guard let self, self.viewIfLoaded?.window != nil else { return }
            self.fetchScreen()
        }
    }

    private func setOwnVariable(_ name: String, to value: String) {
        ownVariables[name] = value
        components.variablesStorage.update(
            cardId: DivCardID(rawValue: screen),
            name: DivVariableName(rawValue: name),
            value: value
        )
    }

    private func show(data: Data) {
        Task { @MainActor in
            await divView.setSource(
                DivViewSource(kind: .data(data), cardId: DivCardID(rawValue: screen)),
                shouldResetPreviousCardData: true
            )
            for (name, value) in ownVariables {
                components.variablesStorage.update(
                    cardId: DivCardID(rawValue: screen),
                    name: DivVariableName(rawValue: name),
                    value: value
                )
            }
            spinner.stopAnimating()
            settleRefresher()
            attachRefresherIfWanted()
        }
    }

    /// Ending a refresh is delicate twice over: endRefreshing() while the
    /// finger still drags (routine against a fast server) corrupts the
    /// control, and even one ended at rest can stop forwarding the pan
    /// gesture, deadening every later pull. So wait for the gesture to
    /// lift, then retire the control and mount a fresh one.
    private func settleRefresher() {
        guard refresher.isRefreshing else { return }
        if let scroll = Self.firstScrollView(in: divView),
           scroll.isTracking || scroll.isDragging {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { [weak self] in
                self?.settleRefresher()
            }
            return
        }
        refresher.endRefreshing()
        if let scroll = Self.firstScrollView(in: divView),
           scroll.refreshControl === refresher {
            scroll.refreshControl = nil
        }
        refresher = makeRefresher()
        attachRefresherIfWanted()
    }

    private func makeRefresher() -> UIRefreshControl {
        let control = UIRefreshControl()
        control.addTarget(self, action: #selector(pulled), for: .valueChanged)
        return control
    }

    /// The gesture rides the screen's own scrolling view (a Gallery): the
    /// control attaches to the first scroll view DivKit rendered, and
    /// re-attaches after every render in case that view was rebuilt.
    private func attachRefresherIfWanted() {
        guard wantsRefresher else { return }
        guard let scroll = Self.firstScrollView(in: divView),
              scroll.refreshControl !== refresher else { return }
        scroll.refreshControl = refresher
    }

    @objc private func pulled() {
        if Server.dev { connect() } else { fetchScreen() }
    }

    private static func firstScrollView(in view: UIView) -> UIScrollView? {
        if let scroll = view as? UIScrollView { return scroll }
        for child in view.subviews {
            if let found = firstScrollView(in: child) { return found }
        }
        return nil
    }

    private func connect() {
        // A re-subscribe (live refetch) must not leak the previous socket.
        socket?.cancel()
        let path = screen.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? screen
        var base = Server.url
        if let scheme = base.range(of: "http") {
            base = base.replacingCharacters(in: scheme, with: "ws")
        }
        guard let url = URL(string: "\(base)/ws/screens/\(path)") else { return }
        var request = URLRequest(url: url)
        Auth.authorize(&request)
        let task = URLSession.shared.webSocketTask(with: request)
        socket = task
        receive(on: task)
        task.resume()
        schedulePing(on: task)
    }

    /// URLSession never pings of its own accord, and a socket that died
    /// without a close reports nothing at all — a dropped network, a NAT or
    /// proxy timeout. Without this a live screen sits on its last render
    /// forever. An unanswered ping cancels the task, which makes receive()
    /// fail and reconnect on the backoff it already has.
    private func schedulePing(on task: URLSessionWebSocketTask) {
        DispatchQueue.main.asyncAfter(deadline: .now() + socketPingInterval) { [weak self] in
            // `state` and not just identity: a cancelled task stays in the
            // field until the reconnect replaces it, and pinging it again
            // every interval would only log the same death twice a minute.
            guard let self, task === self.socket, task.state == .running else { return }
            var answered = false
            task.sendPing { [weak self] error in
                DispatchQueue.main.async {
                    answered = true
                    guard let self, let error, task === self.socket else { return }
                    log.warning("ping for \(self.screen) failed: \(String(describing: error))")
                    task.cancel()
                }
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + socketPingInterval) { [weak self] in
                guard let self, task === self.socket, task.state == .running, !answered else {
                    return
                }
                log.warning("socket for \(self.screen) stopped answering pings")
                task.cancel()
            }
            self.schedulePing(on: task)
        }
    }

    /// Callbacks of a superseded socket can still fire, so each one acts only
    /// when its task is still the one in the `socket` field.
    private func receive(on task: URLSessionWebSocketTask) {
        task.receive { [weak self] result in
            guard let self, task === self.socket else { return }
            switch result {
            case let .success(message):
                self.reconnectDelay = 1
                if case let .string(text) = message, let data = text.data(using: .utf8) {
                    self.show(data: data)
                }
                self.receive(on: task)
            case let .failure(error):
                if task.closeCode.rawValue == notAuthorized {
                    DispatchQueue.main.async { Auth.unauthorized() }
                    return
                }
                log.warning("socket for \(self.screen) failed: \(String(describing: error))")
                // Backs off while the server stays away; a delivered screen
                // resets it.
                let delay = self.reconnectDelay
                self.reconnectDelay = min(delay * 2, 30)
                DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
                    self?.connect()
                }
            }
        }
    }

    private func handle(_ url: URL) {
        guard url.scheme == "latawiec" else { return }
        switch url.host {
        case "navigate":
            if let screen = queryValues(of: url)["screen"] {
                show(screen: screen)
            }
        case "submit":
            var values = queryValues(of: url)
            if let action = values.removeValue(forKey: "action") {
                submit(action: action, values: values)
            }
        case "pick":
            let values = queryValues(of: url)
            if let variable = values["variable"] {
                pendingPickVariable = variable
                if values["source"] == "camera" {
                    shoot()
                } else {
                    var configuration = PHPickerConfiguration()
                    configuration.filter = .images
                    configuration.selectionLimit = 1
                    let picker = PHPickerViewController(configuration: configuration)
                    picker.delegate = self
                    present(picker, animated: true)
                }
            }
        case "locate":
            let values = queryValues(of: url)
            if let variable = values["variable"] {
                pendingLocation = LocationAsk(variable: variable, action: values["action"])
                locationAsks += 1
                requestFix()
            }
        case "unlock":
            var values = queryValues(of: url)
            if let action = values.removeValue(forKey: "action") {
                let reason = values.removeValue(forKey: "reason") ?? ""
                unlock(action: action, values: values, reason: reason)
            }
        case "buy":
            let values = queryValues(of: url)
            if let product = values["product"], let action = values["action"] {
                // The same handler takes anything the store delivers later.
                watchForPurchases(action: action)
                buy(product: product, action: action)
            }
        case "signout":
            Auth.signOut(to: queryValues(of: url)["screen"])
        case "share":
            // Mid-animation double-taps would make the second present a
            // silent no-op anyway; skip it deliberately.
            if let text = queryValues(of: url)["text"], presentedViewController == nil {
                let sheet = UIActivityViewController(
                    activityItems: [text], applicationActivities: nil
                )
                // On an iPad this is a popover, and UIKit refuses to show
                // one with nothing to point at: the tap would be swallowed
                // and, with the guard above, every later tap with it.
                sheet.popoverPresentationController?.sourceView = view
                sheet.popoverPresentationController?.sourceRect = CGRect(
                    x: view.bounds.midX, y: view.bounds.midY, width: 0, height: 0
                )
                sheet.popoverPresentationController?.permittedArrowDirections = []
                present(sheet, animated: true)
            }
        case "open":
            if let target = queryValues(of: url)["url"].flatMap(URL.init(string:)),
               Self.openableSchemes.contains(target.scheme?.lowercased() ?? "") {
                UIApplication.shared.open(target) { [weak self] opened in
                    if !opened { self?.showError("Nothing can open this link") }
                }
            }
        default:
            break
        }
    }

    /// What OpenUrl may leave the app for; anything else is refused.
    private static let openableSchemes: Set<String> = ["http", "https", "mailto", "tel", "sms"]

    private func queryValues(of url: URL) -> [String: String] {
        let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        return Dictionary(items.map { ($0.name, $0.value ?? "") }) { first, _ in first }
    }

    private func show(screen name: String) {
        // A double-tap would stack the same screen twice.
        guard let navigation = navigationController,
              (navigation.topViewController as? ScreenViewController)?.screen != name
        else { return }
        navigation.pushViewController(ScreenViewController(screen: name), animated: true)
    }

    private func requestFix() {
        switch locations.authorizationStatus {
        case .notDetermined:
            // The answer arrives on the delegate, which comes back here.
            locations.requestWhenInUseAuthorization()
        case .restricted, .denied:
            deliverLocation("")
        default:
            locations.requestLocation()
            // requestLocation() does report a failure of its own, but not on
            // a simulator that was never given a location, so time it out.
            let ask = locationAsks
            DispatchQueue.main.asyncAfter(deadline: .now() + fixTimeout) { [weak self] in
                guard let self, self.locationAsks == ask else { return }
                self.deliverLocation("")
            }
        }
    }

    /// First answer (or the timeout) wins; the rest find nothing pending.
    private func deliverLocation(_ value: String) {
        guard let ask = pendingLocation else { return }
        pendingLocation = nil
        setOwnVariable(ask.variable, to: value)
        if let action = ask.action {
            submit(action: action, values: [ask.variable: value])
        }
    }

    /// POSTs the submitted values to the server's action handler and follows
    /// the navigation it answers with. The values arrive in the action URL's
    /// query: the server wrote them there as DivKit expressions, evaluated at
    /// tap time.
    private func submit(
        action: String,
        values: [String: String],
        landed: ((Bool) -> Void)? = nil
    ) {
        let path = action.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? action
        guard let url = URL(string: "\(Server.url)/actions/\(path)") else {
            landed?(false)
            return
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: values)
        Auth.authorize(&request)
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            if let error {
                log.warning("action \(action) failed: \(String(describing: error))")
                landed?(false)
                DispatchQueue.main.async { self?.showError("No connection — try again") }
                return
            }
            let status = (response as? HTTPURLResponse)?.statusCode ?? -1
            if status == 401 {
                landed?(false)
                DispatchQueue.main.async { Auth.unauthorized() }
                return
            }
            guard status == 200, let data else {
                log.warning("action \(action) answered HTTP \(status)")
                landed?(false)
                DispatchQueue.main.async {
                    self?.showError("Something went wrong — try again")
                }
                return
            }
            landed?(true)
            guard let answer = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            else { return }
            // A sign-in action grants the token every later request
            // authenticates with.
            if let granted = answer["token"] as? String {
                Auth.grant(granted)
            }
            guard let screen = answer["navigate"] as? String else { return }
            DispatchQueue.main.async { self?.show(screen: screen) }
        }.resume()
    }
}

extension ScreenViewController: PHPickerViewControllerDelegate {
    func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
        picker.dismiss(animated: true)
        let variable = pendingPickVariable
        pendingPickVariable = nil
        guard let variable, let provider = results.first?.itemProvider else { return }
        let mime = provider.registeredTypeIdentifiers.first
            .flatMap(UTType.init)?.preferredMIMEType ?? "application/octet-stream"
        provider.loadFileRepresentation(forTypeIdentifier: UTType.image.identifier) {
            [weak self] url, error in
            // The temp file dies with this callback, so the bytes are read
            // here, before hopping threads.
            guard let url, let data = try? Data(contentsOf: url) else {
                log.warning("picked photo did not read: \(String(describing: error))")
                DispatchQueue.main.async { self?.showError("Could not read that photo") }
                return
            }
            // Quotes or line breaks in a filename would corrupt the part
            // header; PHPicker names are tame, sanitized anyway.
            let safeName = url.lastPathComponent
                .replacingOccurrences(of: "\"", with: "_")
                .components(separatedBy: .newlines).joined()
            self?.upload(data, name: safeName, mime: mime, into: variable)
        }
    }

    /// The store's flow in front of a submit: the action carries the
    /// receipt, and the server decides what it is worth.
    private func buy(product: String, action: String) {
        Task { @MainActor in
            switch await Store.buy(product) {
            case let .bought(purchase):
                deliver(purchase, to: action)
            case .nothingToReport:
                return
            case let .failed(message):
                showError(message)
            }
        }
    }

    /// A purchase is finished only once the server has its receipt: an
    /// unfinished transaction comes back on the next launch, a finished one
    /// the server never heard about is gone for good.
    private func deliver(_ purchase: StorePurchase, to action: String) {
        submit(action: action, values: purchase.values) { landed in
            guard landed else { return }
            Task { await purchase.finish() }
        }
    }

    /// Ask to Buy approved an hour later, a purchase made on another
    /// device, a redeemed code: StoreKit delivers all of them here and
    /// nowhere else, so a shell that does not listen loses them.
    private func watchForPurchases(action: String) {
        // Read at delivery time, not captured here: a screen with two buy
        // buttons would otherwise hand everything the store recovers to
        // whichever one was tapped first. The Android shell does the same.
        purchaseAction = action
        guard purchaseWatcher == nil else { return }
        purchaseWatcher = Task { [weak self] in
            for await purchase in Store.deliveries() {
                await MainActor.run {
                    guard let self, let latest = self.purchaseAction else { return }
                    self.deliver(purchase, to: latest)
                }
            }
        }
    }

    /// The device's own check — Face ID, Touch ID, or the passcode — in
    /// front of a submit. It gates the tap, not the server: the action
    /// POSTs like any other once the check passes.
    private func unlock(action: String, values: [String: String], reason: String) {
        // Held in a field: a context released mid-evaluation cancels it.
        let context = LAContext()
        unlockContext = context
        // .deviceOwnerAuthentication, not …WithBiometrics: a phone whose
        // owner never set up Face ID still has a passcode.
        guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: nil) else {
            showError(noLock)
            return
        }
        context.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) {
            [weak self] passed, error in
            DispatchQueue.main.async {
                guard let self else { return }
                self.unlockContext = nil
                if passed {
                    self.submit(action: action, values: values)
                    return
                }
                // Every refusal already said its piece in the system sheet,
                // so the shell only records it.
                log.warning("unlock refused: \(String(describing: error))")
            }
        }
    }

    private func shoot() {
        // The simulator claims to have a camera and then shows a blank
        // capture screen, so it is told apart at compile time — the dev loop
        // gets the same message a camera-less device does.
        #if targetEnvironment(simulator)
        let hasCamera = false
        #else
        let hasCamera = UIImagePickerController.isSourceTypeAvailable(.camera)
        #endif
        switch cameraGate(
            status: AVCaptureDevice.authorizationStatus(for: .video),
            hasCamera: hasCamera
        ) {
        case .accessOff:
            pendingPickVariable = nil
            showError("Camera access is off — turn it on in Settings")
            return
        case .missing:
            pendingPickVariable = nil
            showError("This device has no camera")
            return
        case .ready:
            break
        }
        let camera = UIImagePickerController()
        camera.sourceType = .camera
        camera.delegate = self
        present(camera, animated: true)
    }

    /// Ships the picked photo to the server's @app.upload handler and sets
    /// the picker's variable to whatever it returned — the preview and any
    /// Submit pick it up from there.
    private func upload(_ data: Data, name: String, mime: String, into variable: String) {
        guard let url = URL(string: "\(Server.url)/uploads") else { return }
        let boundary = "latawiec-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue(
            "multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type"
        )
        Auth.authorize(&request)
        var body = Data()
        body.append(Data("--\(boundary)\r\n".utf8))
        body.append(
            Data("Content-Disposition: form-data; name=\"file\"; filename=\"\(name)\"\r\n".utf8)
        )
        body.append(Data("Content-Type: \(mime)\r\n\r\n".utf8))
        body.append(data)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        request.httpBody = body
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            let status = (response as? HTTPURLResponse)?.statusCode ?? -1
            if status == 401 {
                DispatchQueue.main.async { Auth.unauthorized() }
                return
            }
            guard error == nil, status == 200, let data,
                  let answer = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let value = answer["value"] as? String
            else {
                log.warning("upload answered HTTP \(status): \(String(describing: error))")
                let message = status == 413 ? "That photo is too big" : "Upload failed — try again"
                DispatchQueue.main.async { self?.showError(message) }
                return
            }
            DispatchQueue.main.async {
                guard let self else { return }
                self.setOwnVariable(variable, to: value)
            }
        }.resume()
    }
}

extension ScreenViewController: CLLocationManagerDelegate {
    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        guard pendingLocation != nil else { return }
        switch manager.authorizationStatus {
        case .notDetermined:
            return
        case .restricted, .denied:
            deliverLocation("")
        default:
            requestFix()
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations fixes: [CLLocation]) {
        guard let fix = fixes.last else { return }
        // String(format:) is unlocalized, so the pair keeps its decimal dots.
        deliverLocation(
            String(
                format: "%.6f,%.6f",
                fix.coordinate.latitude,
                fix.coordinate.longitude
            )
        )
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        log.warning("location failed: \(String(describing: error))")
        deliverLocation("")
    }
}

extension ScreenViewController: UIImagePickerControllerDelegate, UINavigationControllerDelegate {
    func imagePickerController(
        _ picker: UIImagePickerController,
        didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]
    ) {
        let variable = pendingPickVariable
        pendingPickVariable = nil
        let image = info[.originalImage] as? UIImage
        picker.dismiss(animated: true) { [weak self] in
            guard let self, let variable, let image else { return }
            // A camera shot arrives as pixels, not a file: JPEG at 0.9 keeps
            // it indistinguishable while cutting the upload several times
            // over. Encoding a full-resolution frame is slow enough to drop
            // frames, so it happens off the main thread.
            DispatchQueue.global(qos: .userInitiated).async {
                guard let data = image.jpegData(compressionQuality: 0.9) else {
                    DispatchQueue.main.async { self.showError("Could not read that photo") }
                    return
                }
                DispatchQueue.main.async {
                    self.upload(data, name: "shot.jpg", mime: "image/jpeg", into: variable)
                }
            }
        }
    }

    func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
        picker.dismiss(animated: true)
        pendingPickVariable = nil
    }
}
