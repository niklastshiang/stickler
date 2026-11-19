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

/// Builds models with fake cores and a Stickler folder of their own.
@MainActor
final class Harness {
    let defaults: UserDefaults
    let folder: URL
    let uv: URL
    private let made = Made()

    /// What the model asked a core to be made with.
    struct Call {
        let folder: URL
        let tool: URL
        let languages: [String]
    }

    final class Made: @unchecked Sendable {
        let lock = NSLock()
        var cores: [FakeCore] = []
        var calls: [Call] = []
        var bundled: [URL] = []
        var preset: [String: String] = [:]
    }

    /// Every core made from now on answers `command` with `fields` (see `FakeCore.answer`).
    func preset(_ command: String, with fields: String) {
        made.lock.withLock { made.preset[command] = fields }
    }

    var cores: [FakeCore] { made.lock.withLock { made.cores } }
    var calls: [Call] { made.lock.withLock { made.calls } }
    /// The bundled cores the model asked for (an app that brings its own).
    var bundledCalls: [URL] { made.lock.withLock { made.bundled } }
    var core: FakeCore { cores[cores.count - 1] }

    init(stickler: Bool = true) throws {
        defaults = try #require(UserDefaults(suiteName: "stickler-test-\(UUID().uuidString)"))
        let base = FileManager.default.temporaryDirectory
            .appendingPathComponent("stickler-model-\(UUID().uuidString)")
        folder = base.appendingPathComponent("stickler")
        try FileManager.default.createDirectory(
            at: folder.appendingPathComponent("adapters"), withIntermediateDirectories: true)
        if stickler {
            try Data().write(to: folder.appendingPathComponent("pyproject.toml"))
        }
        uv = base.appendingPathComponent("bin/uv")
        try FileManager.default.createDirectory(
            at: uv.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data("#!/bin/sh\n".utf8).write(to: uv)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: uv.path)
    }

    func model(
        uvPlaces: [URL]? = nil, settle: Duration = .milliseconds(300), bundled: URL? = nil
    ) -> AppModel {
        let made = made
        return AppModel(
            defaults: defaults,
            uvPlaces: uvPlaces ?? [URL(fileURLWithPath: "/nonexistent/uv"), uv],
            languages: ["de-DE", "en"],
            settle: settle,
            makeCore: { folder, tool, languages in
                let core = FakeCore()
                made.lock.withLock {
                    for (command, fields) in made.preset {
                        core.answer(command, with: fields)
                    }
                    made.cores.append(core)
                    made.calls.append(Call(folder: folder, tool: tool, languages: languages))
                }
                return core
            },
            bundled: bundled,
            makeBundled: { core, _ in
                let fake = FakeCore()
                made.lock.withLock {
                    made.cores.append(fake)
                    made.bundled.append(core)
                }
                return fake
            })
    }
}

/// Lets the model's listener run until `condition` holds.
@MainActor
func settled(_ condition: () -> Bool) async -> Bool {
    for _ in 0..<500 {
        if condition() { return true }
        try? await Task.sleep(for: .milliseconds(5))
    }
    return condition()
}

let emptyState = #"{"kind": "empty", "can_open": true}"#
let analysing = #"{"kind": "analysing", "song": "/m/a.flac", "name": "a", "steps": [], "#
    + #""can_open": true, "can_cancel": true}"#
