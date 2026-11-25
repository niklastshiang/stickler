import Foundation
import Testing

@testable import SticklerCore

/// A core that records the commands and answers as told; the test sends its events.
final class FakeCore: Core, @unchecked Sendable {
    private let lock = NSLock()
    private var commands: [Command] = []
    private var answers: [String: String] = [:]  // command name → reply line without id
    private var queued: [String: [(String, Duration)]] = [:]  // one-off replies, in order
    private var event: (@Sendable (Incoming) -> Void)?
    private var end: (@Sendable (CoreEnd) -> Void)?
    private(set) var quitWith: Double?

    var sent: [Command] { lock.withLock { commands } }
    /// The commands without the sheet's `settings` at start, which runs beside them.
    var actions: [Command] { sent.filter { $0 != .settings } }

    /// The reply's fields after `"id": …, ` for `command`, e.g. `"ok": true, "minutes": 3`.
    func answer(_ command: String, with fields: String) {
        lock.withLock { answers[command] = fields }
    }

    func start(
        onEvent: @escaping @Sendable (Incoming) -> Void,
        onEnd: @escaping @Sendable (CoreEnd) -> Void
    ) {
        lock.withLock {
            event = onEvent
            end = onEnd
        }
    }

    /// The next `command` gets `fields` after `delay`; later ones get `answer`'s again.
    func queue(_ command: String, with fields: String, after delay: Duration = .zero) {
        lock.withLock { queued[command, default: []].append((fields, delay)) }
    }

    func send(_ command: Command) async throws -> Reply {
        let (fields, delay) = lock.withLock {
            commands.append(command)
            if var waiting = queued[command.name], !waiting.isEmpty {
                let next = waiting.removeFirst()
                queued[command.name] = waiting
                return next
            }
            return (answers[command.name] ?? #""ok": true"#, Duration.zero)
        }
        if delay > .zero {
            try await Task.sleep(for: delay)
        }
        if fields == "not running" {
            throw CoreClientError.notRunning
        }
        let reply = try Reply(line: Data("{\"id\": 1, \(fields)}".utf8))
        if let error = reply.error {
            throw CoreClientError.refused(error)
        }
        return reply
    }

    func quit(seconds: Double) async {
        lock.withLock { quitWith = seconds }
    }

    /// Sends `line` as the core would.
    func emit(_ line: String) throws {
        let incoming = try Incoming(line: Data(line.utf8))
        lock.withLock { event }?(incoming)
    }

    func stop(_ how: CoreEnd) {
        lock.withLock { end }?(how)
    }
}

/// Builds models with fake cores.
@MainActor
final class Harness {
    let defaults: UserDefaults
    private let made = Made()

    final class Made: @unchecked Sendable {
        let lock = NSLock()
        var cores: [FakeCore] = []
        var languages: [[String]] = []
        var preset: [String: String] = [:]
        var late: [String: (String, Duration)] = [:]
    }

    /// Every core made from now on answers `command` with `fields` (see `FakeCore.answer`).
    func preset(_ command: String, with fields: String) {
        made.lock.withLock { made.preset[command] = fields }
    }

    /// Every core made from now on answers its first `command` with `fields` after `delay`.
    func preset(_ command: String, with fields: String, after delay: Duration) {
        made.lock.withLock { made.late[command] = (fields, delay) }
    }

    var cores: [FakeCore] { made.lock.withLock { made.cores } }
    /// The languages each core was made with.
    var languages: [[String]] { made.lock.withLock { made.languages } }
    var core: FakeCore { cores[cores.count - 1] }

    init() throws {
        defaults = try #require(UserDefaults(suiteName: "stickler-test-\(UUID().uuidString)"))
    }

    func model(
        settle: Duration = .milliseconds(300), player: (any Playing)? = nil,
        tick: Duration = .milliseconds(5)
    ) -> AppModel {
        let made = made
        let wanted = ["de-DE", "en"]
        return AppModel(
            defaults: defaults, languages: wanted, settle: settle, player: player, tick: tick
        ) { languages in
            let core = FakeCore()
            made.lock.withLock {
                for (command, fields) in made.preset {
                    core.answer(command, with: fields)
                }
                for (command, (fields, delay)) in made.late {
                    core.queue(command, with: fields, after: delay)
                }
                made.cores.append(core)
                made.languages.append(languages)
            }
            return core
        }
    }
}

/// Lets the model's listener run until `condition` holds: `tries` times 5 ms at most (more
/// for a real process, which a busy runner starts slowly).
@MainActor
func settled(tries: Int = 500, _ condition: () -> Bool) async -> Bool {
    for _ in 0..<tries {
        if condition() { return true }
        try? await Task.sleep(for: .milliseconds(5))
    }
    return condition()
}

let emptyState = #"{"kind": "empty", "can_open": true}"#
let analysing = #"{"kind": "analysing", "song": "/m/a.flac", "name": "a", "steps": [], "#
    + #""can_open": true, "can_cancel": true}"#
