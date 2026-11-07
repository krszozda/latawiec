import DivKit
import UIKit
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
        urlHandler: DivUrlHandlerDelegate { [weak self] url in self?.handle(url) }
    )
    private lazy var divView = DivView(divKitComponents: components)
    private let spinner = UIActivityIndicatorView(style: .large)
    private var socket: URLSessionWebSocketTask?
    private var reconnectDelay: TimeInterval = 1

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
        let cached = ScreenCache.shared.load(screen)
        if let cached {
            show(data: cached.payload)
            if cached.policy == "static" { return }
        }
        let path = screen.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? screen
        guard let url = URL(string: "\(Server.url)/screens/\(path)") else { return }
        var request = URLRequest(url: url)
        Auth.authorize(&request)
        let hadCache = cached != nil
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            guard let self else { return }
            if let error {
                // With a cached copy on screen this is offline mode; a blank
                // screen keeps retrying on the socket's backoff.
                log.warning("screen \(self.screen) fetch failed: \(String(describing: error))")
                if !hadCache { DispatchQueue.main.async { self.retryFetch() } }
                return
            }
            let status = (response as? HTTPURLResponse)?.statusCode ?? -1
            if status == 401 {
                DispatchQueue.main.async { Auth.unauthorized() }
                return
            }
            guard status == 200, let data else {
                log.warning("screen \(self.screen) answered HTTP \(status)")
                if !hadCache { DispatchQueue.main.async { self.retryFetch() } }
                return
            }
            self.reconnectDelay = 1
            let header = (response as? HTTPURLResponse)?
                .value(forHTTPHeaderField: "Cache-Control") ?? ""
            let policy = header.contains("no-store") ? "no-store"
                : header.contains("immutable") ? "static" : "swr"
            if policy != "no-store" {
                ScreenCache.shared.store(self.screen, policy: policy, payload: data)
            }
            self.show(data: data)
        }.resume()
    }

    private func show(data: Data) {
        Task { @MainActor in
            await divView.setSource(
                DivViewSource(kind: .data(data), cardId: DivCardID(rawValue: screen)),
                shouldResetPreviousCardData: true
            )
            spinner.stopAnimating()
        }
    }

    private func connect() {
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
        default:
            break
        }
    }

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
