import UIKit
import os

private let log = Logger(subsystem: "io.github.krszozda.latawiec", category: "shell")

enum Server {
    /// Dev order: the LATAWIEC_SERVER_URL environment variable (simulator,
    /// UI tests), then the URL a store build bakes into Info.plist via the
    /// LATAWIEC_SERVER_URL build setting (see docs/shipping.md), then the
    /// Mac's loopback.
    static let url: String = {
        if let env = ProcessInfo.processInfo.environment["LATAWIEC_SERVER_URL"] {
            return env
        }
        if let baked = Bundle.main.object(forInfoDictionaryKey: "LatawiecServerURL") as? String,
           !baked.isEmpty {
            return baked
        }
        return "http://127.0.0.1:8000"
    }()

    /// Dev keeps the live-reload socket; production fetches and caches.
    static var dev = true
}

private struct Manifest: Decodable {
    struct Tab: Decodable {
        let screen: String
        let title: String
        let icon: String?
    }

    struct Theme: Decodable {
        let accent: String
    }

    let tabs: [Tab]
    let theme: Theme?
    let login: String?
    let version: String?
    let dev: Bool?
}

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?

    /// Tab root screens in bar order; a deep link to one selects its tab.
    private var tabScreens: [String] = []

    /// A deep link that arrived before the manifest; opened once it applies.
    private var pendingDeepLink: String?
    private var manifestApplied = false

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {
        // UI tests reset the persisted token to start every run signed out.
        if ProcessInfo.processInfo.environment["LATAWIEC_RESET_AUTH"] != nil {
            TokenStore.clear()
            Auth.token = nil
        }
        let window = UIWindow(frame: UIScreen.main.bounds)
        window.rootViewController = UIViewController()
        window.rootViewController?.view.backgroundColor = .systemBackground
        window.makeKeyAndVisible()
        self.window = window
        loadManifest()
        return true
    }

    func application(
        _ app: UIApplication,
        open url: URL,
        options: [UIApplication.OpenURLOptionsKey: Any] = [:]
    ) -> Bool {
        guard let screen = Self.screenPath(url) else { return false }
        openDeepLink(screen)
        return true
    }

    /// Universal Links land here once a branded build adds the Associated
    /// Domains entitlement (see docs/shipping.md).
    func application(
        _ application: UIApplication,
        continue userActivity: NSUserActivity,
        restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void
    ) -> Bool {
        guard userActivity.activityType == NSUserActivityTypeBrowsingWeb,
              let url = userActivity.webpageURL,
              let screen = Self.screenPath(url)
        else { return false }
        openDeepLink(screen)
        return true
    }

    /// Maps a deep-link URL to a screen path. Universal Links carry the
    /// screen in the https path; a custom scheme starts it at the host, so
    /// "latawiec://product/42" opens the screen "product/42". The link is
    /// untrusted: one whose decoded segments could reshape the request path
    /// they end up in is dropped.
    static func screenPath(_ url: URL) -> String? {
        let path = url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let screen: String
        if url.scheme?.lowercased() == "http" || url.scheme?.lowercased() == "https" {
            screen = path
        } else {
            screen = [url.host ?? "", path].filter { !$0.isEmpty }.joined(separator: "/")
        }
        guard !screen.isEmpty else { return nil }
        let segments = screen.components(separatedBy: "/")
        guard segments.allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." }) else { return nil }
        return screen
    }

    /// A tab root selects its tab; any other screen pushes onto the stack.
    private func openDeepLink(_ screen: String) {
        guard manifestApplied else {
            pendingDeepLink = screen
            return
        }
        let tabBar = window?.rootViewController as? UITabBarController
        if let tabBar, let index = tabScreens.firstIndex(of: screen) {
            tabBar.selectedIndex = index
            // The link means the root itself, like Android's showRoot — also
            // when the tab was already selected with screens pushed on top.
            (tabBar.selectedViewController as? UINavigationController)?
                .popToRootViewController(animated: false)
            return
        }
        guard let navigation = tabBar?.selectedViewController as? UINavigationController
            ?? window?.rootViewController as? UINavigationController
        else { return }
        // A repeated link would stack the same screen twice and break back.
        if (navigation.topViewController as? ScreenViewController)?.screen != screen {
            navigation.pushViewController(ScreenViewController(screen: screen), animated: true)
        }
    }

    private func loadManifest() {
        guard let url = URL(string: "\(Server.url)/manifest") else {
            window?.rootViewController = Self.fallbackRoot()
            return
        }
        // The default 60s timeout would leave the window blank that long on an
        // unreachable host; fail fast and let the screen's socket reconnect.
        var request = URLRequest(url: url)
        request.timeoutInterval = 5
        URLSession.shared.dataTask(with: request) { [weak self] data, _, _ in
            // Offline boot runs on the last manifest the shell saw.
            let raw = data ?? ScreenCache.shared.loadManifest()
            let manifest = raw.flatMap { try? JSONDecoder().decode(Manifest.self, from: $0) }
            DispatchQueue.main.async {
                guard let self else { return }
                Auth.loginScreen = manifest?.login
                if let manifest, let raw {
                    Server.dev = manifest.dev ?? true
                    // Cached screens may be rendered per locale, so a
                    // language change drops them exactly like a version bump.
                    let languages = Locale.preferredLanguages.joined(separator: ",")
                    ScreenCache.shared.adoptVersion("\(manifest.version ?? "")|\(languages)")
                    ScreenCache.shared.storeManifest(raw)
                }
                if let manifest, !manifest.tabs.isEmpty {
                    self.tabScreens = manifest.tabs.map(\.screen)
                    self.window?.rootViewController = Self.tabBarController(for: manifest)
                } else {
                    if manifest == nil {
                        log.warning("manifest unavailable; falling back to home")
                    }
                    self.window?.rootViewController = Self.fallbackRoot()
                }
                self.manifestApplied = true
                if let screen = self.pendingDeepLink {
                    self.pendingDeepLink = nil
                    self.openDeepLink(screen)
                }
            }
        }.resume()
    }

    private static func fallbackRoot() -> UIViewController {
        UINavigationController(rootViewController: ScreenViewController(screen: "home"))
    }

    private static func tabBarController(for manifest: Manifest) -> UITabBarController {
        let controller = UITabBarController()
        controller.viewControllers = manifest.tabs.map { tab in
            let navigation = UINavigationController(
                rootViewController: ScreenViewController(screen: tab.screen)
            )
            navigation.tabBarItem.title = tab.title
            if let icon = tab.icon {
                loadIcon(at: icon, into: navigation.tabBarItem)
            }
            return navigation
        }
        if let accent = manifest.theme.flatMap({ color(hex: $0.accent) }) {
            controller.tabBar.tintColor = accent
        }
        return controller
    }

    private static func loadIcon(at path: String, into item: UITabBarItem) {
        guard let url = URL(string: "\(Server.url)\(path)") else { return }
        URLSession.shared.dataTask(with: url) { data, _, error in
            guard let data, let image = UIImage(data: data) else {
                log.warning("tab icon \(path) failed: \(String(describing: error))")
                return
            }
            let scale = 25 / max(image.size.width, image.size.height, 1)
            let size = CGSize(
                width: image.size.width * scale,
                height: image.size.height * scale
            )
            let scaled = UIGraphicsImageRenderer(size: size).image { _ in
                image.draw(in: CGRect(origin: .zero, size: size))
            }
            DispatchQueue.main.async {
                item.image = scaled.withRenderingMode(.alwaysTemplate)
            }
        }.resume()
    }

    private static func color(hex: String) -> UIColor? {
        guard hex.hasPrefix("#"), hex.count == 7,
              let rgb = UInt32(hex.dropFirst(), radix: 16)
        else { return nil }
        return UIColor(
            red: CGFloat((rgb >> 16) & 0xFF) / 255,
            green: CGFloat((rgb >> 8) & 0xFF) / 255,
            blue: CGFloat(rgb & 0xFF) / 255,
            alpha: 1
        )
    }
}
