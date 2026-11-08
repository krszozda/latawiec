import DivKit
import PhotosUI
import UIKit
import UniformTypeIdentifiers
import os

private let log = Logger(subsystem: "io.github.krszozda.latawiec", category: "shell")

/// The server's WebSocket close code for a missing or rejected token.
private let notAuthorized = 4401

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

    private lazy var refresher = makeRefresher()
    private var wantsRefresher = false

    init(screen: String) {
        self.screen = screen
        super.init(nibName: nil, bundle: nil)
        title = screen
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }

    deinit {
        socket?.cancel()
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
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

    private func show(data: Data) {
        Task { @MainActor in
            await divView.setSource(
                DivViewSource(kind: .data(data), cardId: DivCardID(rawValue: screen)),
                shouldResetPreviousCardData: true
            )
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
            if let variable = queryValues(of: url)["variable"] {
                pendingPickVariable = variable
                var configuration = PHPickerConfiguration()
                configuration.filter = .images
                configuration.selectionLimit = 1
                let picker = PHPickerViewController(configuration: configuration)
                picker.delegate = self
                present(picker, animated: true)
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

    /// POSTs the submitted values to the server's action handler and follows
    /// the navigation it answers with. The values arrive in the action URL's
    /// query: the server wrote them there as DivKit expressions, evaluated at
    /// tap time.
    private func submit(action: String, values: [String: String]) {
        let path = action.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? action
        guard let url = URL(string: "\(Server.url)/actions/\(path)") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: values)
        Auth.authorize(&request)
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            if let error {
                log.warning("action \(action) failed: \(String(describing: error))")
                DispatchQueue.main.async { self?.showError("No connection — try again") }
                return
            }
            let status = (response as? HTTPURLResponse)?.statusCode ?? -1
            if status == 401 {
                DispatchQueue.main.async { Auth.unauthorized() }
                return
            }
            guard status == 200, let data else {
                log.warning("action \(action) answered HTTP \(status)")
                DispatchQueue.main.async {
                    self?.showError("Something went wrong — try again")
                }
                return
            }
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
                self.components.variablesStorage.update(
                    cardId: DivCardID(rawValue: self.screen),
                    name: DivVariableName(rawValue: variable),
                    value: value
                )
            }
        }.resume()
    }
}
