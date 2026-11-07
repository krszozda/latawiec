import UIKit
import os

private let log = Logger(subsystem: "io.github.krszozda.latawiec", category: "shell")

enum Server {
    /// The simulator reaches the Mac's loopback directly; on a device, launch
    /// with the LATAWIEC_SERVER_URL environment variable set to the Mac's LAN
    /// address.
    static let url = ProcessInfo.processInfo.environment["LATAWIEC_SERVER_URL"]
        ?? "http://127.0.0.1:8000"
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
}

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {
        let window = UIWindow(frame: UIScreen.main.bounds)
        window.rootViewController = UIViewController()
        window.rootViewController?.view.backgroundColor = .systemBackground
        window.makeKeyAndVisible()
        self.window = window
        loadManifest()
        return true
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
            let manifest = data.flatMap { try? JSONDecoder().decode(Manifest.self, from: $0) }
            DispatchQueue.main.async {
                guard let self else { return }
                if let manifest, !manifest.tabs.isEmpty {
                    self.window?.rootViewController = Self.tabBarController(for: manifest)
                } else {
                    if manifest == nil {
                        log.warning("manifest unavailable; falling back to home")
                    }
                    self.window?.rootViewController = Self.fallbackRoot()
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
