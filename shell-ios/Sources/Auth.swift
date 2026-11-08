import Foundation
import Security
import UIKit
import os

private let log = Logger(subsystem: "io.github.krszozda.latawiec", category: "shell")

/// Persists the auth token in the Keychain, which encrypts it at rest.
enum TokenStore {
    private static let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: "io.github.krszozda.latawiec",
        kSecAttrAccount as String: "token",
    ]

    static func load() -> String? {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(request as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data
        else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func save(_ token: String) {
        let data = Data(token.utf8)
        var attributes = query
        attributes[kSecValueData as String] = data
        var status = SecItemAdd(attributes as CFDictionary, nil)
        if status == errSecDuplicateItem {
            status = SecItemUpdate(
                query as CFDictionary,
                [kSecValueData as String: data] as CFDictionary
            )
        }
        if status != errSecSuccess {
            log.warning("token was not saved: \(status)")
        }
    }

    static func clear() {
        SecItemDelete(query as CFDictionary)
    }
}

/// The session's auth state, shared by every screen.
enum Auth {
    static var token: String? = TokenStore.load()

    /// Screen from the manifest to show when the server answers 401/4401.
    static var loginScreen: String?

    static func grant(_ token: String) {
        // A new identity must not inherit the previous one's cached screens.
        ScreenCache.shared.clear()
        self.token = token
        TokenStore.save(token)
    }

    /// Every screen and action request carries the token and device context.
    static func authorize(_ request: inout URLRequest) {
        if let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.setValue(
            Locale.preferredLanguages.joined(separator: ","),
            forHTTPHeaderField: "Accept-Language"
        )
        request.setValue("ios", forHTTPHeaderField: "X-Latawiec-Platform")
        request.setValue(TimeZone.current.identifier, forHTTPHeaderField: "X-Latawiec-Timezone")
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString")
        request.setValue(version as? String ?? "", forHTTPHeaderField: "X-Latawiec-App-Version")
    }

    /// A rejected token is gone for good; the login screen starts over.
    static func unauthorized() {
        token = nil
        TokenStore.clear()
        // The identity ended, so its cached screens must go with it.
        ScreenCache.shared.clear()
        guard let login = loginScreen else {
            log.warning("server answered 401 and the manifest names no login screen")
            return
        }
        restart(on: login)
    }

    /// The user chose to leave: token and cached screens go together.
    static func signOut(to screen: String?) {
        token = nil
        TokenStore.clear()
        ScreenCache.shared.clear()
        restart(on: screen ?? loginScreen ?? "home")
    }

    private static func restart(on screen: String) {
        let window = (UIApplication.shared.delegate as? AppDelegate)?.window
        window?.rootViewController = UINavigationController(
            rootViewController: ScreenViewController(screen: screen)
        )
    }
}
