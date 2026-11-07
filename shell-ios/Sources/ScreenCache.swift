import CryptoKit
import Foundation
import os

private let log = Logger(subsystem: "io.github.krszozda.latawiec", category: "shell")

/// Last-known screens on disk, keyed by screen path and invalidated as a
/// whole when the server's manifest version changes. Each file starts with
/// the screen's cache policy on its own line, so a "static" hit can skip
/// revalidation until the version moves.
final class ScreenCache {
    static let shared = ScreenCache()

    struct Entry {
        let policy: String
        let payload: Data
    }

    private let dir: URL
    private let defaults = UserDefaults.standard

    init() {
        let support = FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask
        )[0]
        dir = support.appendingPathComponent("screens", isDirectory: true)
    }

    /// The last manifest the shell saw; offline starts boot from it.
    func storeManifest(_ manifest: Data) {
        defaults.set(manifest, forKey: "latawiec.manifest")
    }

    func loadManifest() -> Data? {
        defaults.data(forKey: "latawiec.manifest")
    }

    /// Drops every cached screen when the served version changes.
    func adoptVersion(_ version: String?) {
        if defaults.string(forKey: "latawiec.version") == version { return }
        try? FileManager.default.removeItem(at: dir)
        defaults.set(version, forKey: "latawiec.version")
    }

    func load(_ name: String) -> Entry? {
        let url = file(name)
        guard let content = try? Data(contentsOf: url) else { return nil }
        guard let split = content.firstIndex(of: UInt8(ascii: "\n")),
              let policy = String(data: content[..<split], encoding: .utf8),
              case let payload = Data(content[content.index(after: split)...]),
              // A truncated write must land here, not crash the render loop.
              (try? JSONSerialization.jsonObject(with: payload)) != nil
        else {
            log.warning("cached screen \(name) did not read; dropping it")
            try? FileManager.default.removeItem(at: url)
            return nil
        }
        return Entry(policy: policy, payload: payload)
    }

    func store(_ name: String, policy: String, payload: Data) {
        do {
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            var content = Data("\(policy)\n".utf8)
            content.append(payload)
            try content.write(to: file(name), options: .atomic)
        } catch {
            log.warning("screen \(name) was not cached: \(String(describing: error))")
        }
    }

    // Screen paths may hold slashes and params; the digest makes a safe name.
    private func file(_ name: String) -> URL {
        let digest = SHA256.hash(data: Data(name.utf8))
        let hex = digest.map { String(format: "%02x", $0) }.joined()
        return dir.appendingPathComponent(hex + ".json")
    }
}
