import UIKit

/// The manifest theme on the native chrome; a nil color keeps the
/// platform's own, which follows the system's light or dark mode.
enum Chrome {
    static var accent: UIColor?
    static var background: UIColor?
    static var bar: UIColor?

    static func adopt(accent: String?, background: String?, bar: String?) {
        self.accent = accent.flatMap(color(hex:))
        self.background = background.flatMap(color(hex:))
        self.bar = bar.flatMap(color(hex:))
    }

    static func color(hex: String) -> UIColor? {
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

    /// Whether dark icons and text read on `color`: WCAG relative luminance
    /// over one half, the same line Android's ColorUtils draws.
    static func isLight(_ color: UIColor) -> Bool {
        var red: CGFloat = 0, green: CGFloat = 0, blue: CGFloat = 0, alpha: CGFloat = 0
        color.getRed(&red, green: &green, blue: &blue, alpha: &alpha)
        func linear(_ channel: CGFloat) -> CGFloat {
            channel <= 0.04045 ? channel / 12.92 : pow((channel + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue) > 0.5
    }

    static var screenBackground: UIColor { background ?? .systemBackground }

    /// Status-bar icons that read on whatever is behind them.
    static func statusBarStyle(over color: UIColor?) -> UIStatusBarStyle {
        guard let color else { return .default }
        return isLight(color) ? .darkContent : .lightContent
    }

    static func style(_ tabBar: UITabBar) {
        let appearance = UITabBarAppearance()
        if let bar {
            appearance.configureWithOpaqueBackground()
            appearance.backgroundColor = bar
            // Unselected tabs in the same muted colors Android uses.
            let idle = isLight(bar) ? UIColor.gray : UIColor.white.withAlphaComponent(0.55)
            for layout in [
                appearance.stackedLayoutAppearance,
                appearance.inlineLayoutAppearance,
                appearance.compactInlineLayoutAppearance,
            ] {
                layout.normal.iconColor = idle
                layout.normal.titleTextAttributes = [.foregroundColor: idle]
            }
        } else {
            appearance.configureWithDefaultBackground()
        }
        tabBar.standardAppearance = appearance
        tabBar.scrollEdgeAppearance = appearance
        tabBar.tintColor = accent
    }

    static func style(_ navigationBar: UINavigationBar) {
        let appearance = UINavigationBarAppearance()
        if let bar {
            appearance.configureWithOpaqueBackground()
            appearance.backgroundColor = bar
            appearance.shadowColor = .clear
        } else {
            appearance.configureWithDefaultBackground()
        }
        navigationBar.standardAppearance = appearance
        navigationBar.scrollEdgeAppearance = appearance
        navigationBar.compactAppearance = appearance
        navigationBar.tintColor = accent
    }

    /// A theme that changed mid-session reaches what is already on screen.
    static func restyle(_ root: UIViewController?) {
        guard let root else { return }
        if let tabs = root as? UITabBarController {
            style(tabs.tabBar)
            tabs.viewControllers?.forEach(restyle)
        } else if let stack = root as? UINavigationController {
            style(stack.navigationBar)
            stack.viewControllers.forEach(restyle)
        } else if let screen = root as? ScreenViewController, screen.isViewLoaded {
            screen.view.backgroundColor = screenBackground
        }
        root.setNeedsStatusBarAppearanceUpdate()
    }
}

/// A screen stack that shows its bar only once there is somewhere to go
/// back to. A root screen owns the whole top of the display: no system
/// title above the app's own header, which is how the Android shell looks.
final class StackController: UINavigationController, UINavigationControllerDelegate {
    override init(rootViewController: UIViewController) {
        super.init(rootViewController: rootViewController)
        delegate = self
        Chrome.style(navigationBar)
        setNavigationBarHidden(true, animated: false)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }

    func navigationController(
        _ navigationController: UINavigationController,
        willShow viewController: UIViewController,
        animated: Bool
    ) {
        setNavigationBarHidden(viewController === viewControllers.first, animated: animated)
        setNeedsStatusBarAppearanceUpdate()
    }

    // Under a shown bar the icons sit on the bar; otherwise on the screen.
    override var childForStatusBarStyle: UIViewController? {
        isNavigationBarHidden ? topViewController : nil
    }

    override var preferredStatusBarStyle: UIStatusBarStyle {
        Chrome.statusBarStyle(over: Chrome.bar ?? Chrome.background)
    }
}
