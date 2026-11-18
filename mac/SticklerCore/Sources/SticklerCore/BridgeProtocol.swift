/// The version of the line protocol this client speaks (`docs/bridge.md`, the `hello` event).
public enum BridgeProtocol {
    public static let version = 1

    /// Whether a core that says `version` in its `hello` can be talked to. Another version
    /// means the app and its core come from different releases: the window says so instead of
    /// misreading lines.
    public static func speaks(_ version: Int) -> Bool {
        version == self.version
    }
}
