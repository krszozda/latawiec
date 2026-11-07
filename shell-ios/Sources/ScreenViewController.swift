import DivKit
import UIKit
import os

private let log = Logger(subsystem: "io.github.krszozda.latawiec", category: "shell")

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
    private var socket: URLSessionWebSocketTask?

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
        connect()
    }

    private func connect() {
        let path = screen.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? screen
        var base = Server.url
        if let scheme = base.range(of: "http") {
            base = base.replacingCharacters(in: scheme, with: "ws")
        }
        guard let url = URL(string: "\(base)/ws/screens/\(path)") else { return }
        let task = URLSession.shared.webSocketTask(with: url)
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
                if case let .string(text) = message, let data = text.data(using: .utf8) {
                    Task { @MainActor in
                        await self.divView.setSource(
                            DivViewSource(kind: .data(data), cardId: DivCardID(rawValue: self.screen)),
                            shouldResetPreviousCardData: true
                        )
                    }
                }
                self.receive(on: task)
            case let .failure(error):
                log.warning("socket for \(self.screen) failed: \(String(describing: error))")
                DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
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
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            if let error {
                log.warning("action \(action) failed: \(String(describing: error))")
                return
            }
            let status = (response as? HTTPURLResponse)?.statusCode ?? -1
            guard status == 200, let data else {
                log.warning("action \(action) answered HTTP \(status)")
                return
            }
            guard let answer = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let screen = answer["navigate"] as? String
            else { return }
            DispatchQueue.main.async { self?.show(screen: screen) }
        }.resume()
    }
}
