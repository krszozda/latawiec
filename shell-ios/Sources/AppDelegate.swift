import UIKit

enum Server {
    /// The simulator reaches the Mac's loopback directly; on a device, launch
    /// with the LATAWIEC_SERVER_URL environment variable set to the Mac's LAN
    /// address.
    static let url = ProcessInfo.processInfo.environment["LATAWIEC_SERVER_URL"]
        ?? "http://127.0.0.1:8000"
}

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {
        let window = UIWindow(frame: UIScreen.main.bounds)
        window.rootViewController = UINavigationController(
            rootViewController: ScreenViewController(screen: "home")
        )
        window.makeKeyAndVisible()
        self.window = window
        return true
    }
}
