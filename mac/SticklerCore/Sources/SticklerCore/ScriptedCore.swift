import Foundation

/// A core that plays fixed lines (`docs/bridge.md`), for the app's previews and screenshots:
/// each screen drawn from the very lines the real core sends. Every command is answered with
/// `ok`, or with the reply set for its name.
public final class ScriptedCore: Core, @unchecked Sendable {
    private let lines: [String]
    private let replies: [String: String]
    private let lock = NSLock()
    private var commands: [Command] = []

    /// `replies`: a command's name → its reply's fields after the id, e.g. `"ok": true, …`.
    public init(lines: [String], replies: [String: String] = [:]) {
        self.lines = lines
        self.replies = replies
    }

    /// The commands sent so far.
    public var sent: [Command] { lock.withLock { commands } }

    public func start(
        onEvent: @escaping @Sendable (Incoming) -> Void,
        onEnd _: @escaping @Sendable (CoreEnd) -> Void
    ) {
        for line in lines {
            if let incoming = try? Incoming(line: Data(line.utf8)) {
                onEvent(incoming)
            }
        }
    }

    public func send(_ command: Command) async throws -> Reply {
        lock.withLock { commands.append(command) }
        let fields = replies[command.name] ?? #""ok": true"#
        let reply = try Reply(line: Data("{\"id\": 0, \(fields)}".utf8))
        if let error = reply.error {
            throw CoreClientError.refused(error)
        }
        return reply
    }

    public func quit(seconds _: Double) async {}
}
