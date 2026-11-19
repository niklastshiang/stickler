import Foundation
import Testing

@testable import SticklerCore

#if canImport(Glibc)
import Glibc
#endif

// The client against the real bridge with stand-in models (scripts/bridge_stand_ins.py, the same
// ones as tests/app/test_bridge_process.py), and against small fake cores written in Python.

let repository = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    .deletingLastPathComponent().deletingLastPathComponent()

/// `uv`, as the app looks for it: on PATH or in ~/.local/bin.
func uv() throws -> URL {
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    let folders = (ProcessInfo.processInfo.environment["PATH"] ?? "").split(separator: ":")
        .map(String.init) + ["\(home)/.local/bin"]
    let found = folders.map { URL(fileURLWithPath: $0).appendingPathComponent("uv") }
        .first { FileManager.default.isExecutableFile(atPath: $0.path) }
    return try #require(found, "uv is needed for these tests (CONSTRAINTS.md: Swift tests)")
}

struct StandIns: Decodable, Sendable {
    let models: String
    let song: String

    /// Set up once for all tests (uv sync of two tiny environments, offline).
    static let shared: Result<StandIns, any Error> = Result {
        let folder = FileManager.default.temporaryDirectory
            .appendingPathComponent("stickler-stand-ins-\(UUID().uuidString)")
        let process = Process()
        process.executableURL = try uv()
        process.arguments = ["run", "python", "scripts/bridge_stand_ins.py", folder.path]
        process.currentDirectoryURL = repository
        let out = Pipe()
        process.standardOutput = out
        try process.run()
        let data = out.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return try JSONDecoder().decode(StandIns.self, from: data)
    }
}

/// Collects what the client reports, from its threads.
final class Recorder: @unchecked Sendable {
    private let lock = NSLock()
    private var incoming: [Incoming] = []
    private var end: CoreEnd?

    var events: [Incoming] { lock.withLock { incoming } }
    var ended: CoreEnd? { lock.withLock { end } }

    func event(_ line: Incoming) { lock.withLock { incoming.append(line) } }
    func finished(_ how: CoreEnd) { lock.withLock { end = how } }

    func states() -> [AppState] {
        events.compactMap {
            if case .event(_, .state(let state)) = $0 { return state }
            return nil
        }
    }

    func start(_ client: CoreClient) {
        client.start(onEvent: event, onEnd: finished)
    }
}

/// Waits until `condition` holds, at most `seconds`.
func eventually(_ seconds: Double = 30, _ condition: () -> Bool) async -> Bool {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline {
        if condition() { return true }
        try? await Task.sleep(for: .milliseconds(20))
    }
    return condition()
}

/// The real bridge with the stand-ins, its files in a folder of its own.
func bridge() throws -> CoreClient {
    let models = try StandIns.shared.get().models
    let home = FileManager.default.temporaryDirectory
        .appendingPathComponent("stickler-home-\(UUID().uuidString)").path
    return CoreClient(
        executable: try uv(), arguments: ["run", "stickler-bridge"], directory: repository,
        environment: [
            "STICKLER_ADAPTERS": models, "STICKLER_RESULTS_CACHE": "\(home)/results",
            "XDG_DATA_HOME": "\(home)/data", "XDG_CONFIG_HOME": "\(home)/config",
            "XDG_CACHE_HOME": "\(home)/cache", "LANGUAGE": "en"
        ])
}

/// A fake core: `python3 -c code`.
func fakeCore(_ code: String) -> CoreClient {
    CoreClient(executable: URL(fileURLWithPath: "/usr/bin/env"), arguments: ["python3", "-c", code])
}

/// The core's own process: `uv run` starts the bridge as its child (a SIGKILL to uv would leave
/// the bridge running; a crash of the bridge ends uv too).
func bridgeProcess(under uvPID: Int32) async throws -> Int32 {
    var found: Int32?
    _ = await eventually(10) {
        let pgrep = Process()
        pgrep.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        pgrep.arguments = ["pgrep", "-P", "\(uvPID)"]
        let out = Pipe()
        pgrep.standardOutput = out
        guard (try? pgrep.run()) != nil else { return false }
        pgrep.waitUntilExit()
        let text = String(bytes: out.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)
        found = text?.split(separator: "\n").first.flatMap { Int32($0) }
        return found != nil
    }
    return try #require(found, "no child of uv \(uvPID)")
}

@Suite(.serialized, .timeLimit(.minutes(1))) struct RealBridge {
    @Test func aSongBecomesAResultAndItsPagesAndQuitEndsTheCore() async throws {
        let song = try StandIns.shared.get().song
        let client = try bridge()
        let seen = Recorder()
        seen.start(client)
        #expect(await eventually { seen.states().first?.screen == .empty })
        guard case .hello(let hello)? = seen.events.first else {
            Issue.record("the first line is not hello: \(seen.events)")
            return
        }
        #expect(hello.protocol == BridgeProtocol.version && hello.language == "en")
        #expect(seen.events.contains { if case .event(_, .recent) = $0 { true } else { false } })

        _ = try await client.send(.open(path: song))
        #expect(await eventually {
            if case .result = seen.states().last?.screen { true } else { false }
        })
        guard case .result(let result)? = seen.states().last?.screen else { return }
        #expect(result.title == "Groove" && result.meter == [4, 4] && result.tempo == 120)
        let seqs = seen.events.compactMap { if case .event(let seq, _) = $0 { seq } else { nil } }
        #expect(seqs == Array(1...seqs.count))  // every event, in order

        let pages = try await client.send(.pages(width: 800, zoom: nil)).payload(Pages.self)
        #expect(pages.pages.first?.svg.hasPrefix("<svg") == true)
        #expect(pages.pages.first?.bars.first?.bar == 1)

        await #expect(throws: CoreClientError.self) { try await client.send(.cancel) }
        do {
            _ = try await client.send(.agree)
        } catch CoreClientError.refused(let error) {
            #expect(error.code == .notNow && !error.message.isEmpty)
        }

        await client.quit()
        #expect(await eventually { seen.ended != nil })
        #expect(seen.ended?.reason == .exited(0))
        #expect(!client.isRunning)
        await #expect(throws: CoreClientError.notRunning) { try await client.send(.start) }
    }

    @Test func aKilledCoreIsReportedAndNoLongerTakesCommands() async throws {
        let client = try bridge()
        let seen = Recorder()
        seen.start(client)
        #expect(await eventually { !seen.states().isEmpty })
        let core = try await bridgeProcess(under: try #require(client.processIdentifier))
        kill(core, SIGKILL)
        #expect(await eventually { seen.ended != nil })
        // uv reports its child's signal as its own end: 128 + 9, or the signal itself
        let reason = seen.ended?.reason
        #expect(reason == .exited(128 + SIGKILL) || reason == .signalled(SIGKILL), "\(reason)")
        await #expect(throws: CoreClientError.notRunning) { try await client.send(.start) }
    }
}

@Test(.timeLimit(.minutes(1))) func aCoreOfAnotherProtocolVersionIsEnded() async {
    let client = fakeCore("""
        import sys, time
        print('{"event": "hello", "protocol": 99, "version": "99", "language": "en"}', flush=True)
        time.sleep(30)
        """)
    let seen = Recorder()
    seen.start(client)
    #expect(await eventually(10) { seen.ended != nil })
    #expect(seen.ended?.reason == .wrongProtocol(99))
    #expect(seen.events.isEmpty)  // its hello is not passed on
}

@Test(.timeLimit(.minutes(1))) func theEndKeepsTheStatusAndTheLastLinesOfStderr() async {
    let client = fakeCore("""
        import sys
        for k in range(50):
            print(f"line {k}", file=sys.stderr)
        print("not a protocol line", flush=True)
        sys.exit(3)
        """)
    let seen = Recorder()
    seen.start(client)
    #expect(await eventually(10) { seen.ended != nil })
    let end = seen.ended
    #expect(end?.reason == .exited(3))
    let details = end?.details ?? []
    #expect(details.count == CoreClient.detailLines + 1)  // stderr's last 40, then the line
    #expect(details.first == "line 10" && details[CoreClient.detailLines - 1] == "line 49")
    #expect(details.last == "unreadable line from the core: not a protocol line")
}

@Test(.timeLimit(.minutes(1))) func aLongLineArrivesWhole() async {
    let client = fakeCore("""
        import json, time
        text = "x" * 1_000_000
        print(json.dumps({"event": "notice", "seq": 1, "text": text, "opens": None}), flush=True)
        time.sleep(30)
        """)
    let seen = Recorder()
    seen.start(client)
    #expect(await eventually(10) { !seen.events.isEmpty })
    if case .event(1, .notice(let notice))? = seen.events.first {
        #expect(notice.text.count == 1_000_000 && notice.opens == nil)
    } else {
        Issue.record("no notice: \(seen.events)")
    }
    client.terminate()
    #expect(await eventually(10) { seen.ended != nil })
}

@Test(.timeLimit(.minutes(1))) func aCoreThatEndsBeforeItsReplyFailsTheCommand() async {
    let client = fakeCore("import sys; sys.stdin.readline(); sys.exit(1)")
    let seen = Recorder()
    seen.start(client)
    await #expect(throws: CoreClientError.notRunning) { try await client.send(.start) }
    #expect(await eventually(10) { seen.ended?.reason == .exited(1) })
}

@Test func aCoreThatCannotStartIsReportedAtOnce() {
    let client = CoreClient(
        executable: URL(fileURLWithPath: "/nonexistent/uv"), arguments: ["run", "stickler-bridge"])
    let seen = Recorder()
    seen.start(client)
    guard case .notStarted? = seen.ended?.reason else {
        Issue.record("not reported: \(String(describing: seen.ended))")
        return
    }
    #expect(!client.isRunning && client.processIdentifier == nil)
}

@Test(.timeLimit(.minutes(1))) func nothingIsSentBeforeTheStart() async {
    let client = fakeCore("pass")
    await #expect(throws: CoreClientError.notRunning) { try await client.send(.start) }
}

@Test(.timeLimit(.minutes(1))) func theCoreStartsWithNoSignalBlocked() async {
    // Started from a test's thread (Swift's concurrency pool blocks signals there): without
    // the client's clean start the core would not hear SIGTERM.
    let client = fakeCore("""
        import json, signal, time
        blocked = sorted(int(s) for s in signal.pthread_sigmask(signal.SIG_BLOCK, []))
        line = {"event": "notice", "seq": 1, "text": str(blocked), "opens": None}
        print(json.dumps(line), flush=True)
        time.sleep(30)
        """)
    let seen = Recorder()
    seen.start(client)
    #expect(await eventually(10) { !seen.events.isEmpty })
    #expect(seen.events.first == .event(seq: 1, .notice(Notice(text: "[]", opens: nil))))
    client.terminate()  // SIGTERM ends it
    #expect(await eventually(10) { seen.ended?.reason == .signalled(SIGTERM) })
}

@Test func theMacAppsCoreRunsAsAnInstalledAppFromTheChosenFolder() {
    let folder = URL(fileURLWithPath: "/Users/me/stickler")
    let client = CoreClient.bridge(
        in: folder, uv: URL(fileURLWithPath: "/opt/homebrew/bin/uv"), languages: ["de-DE", "en"],
        path: "/usr/bin:/bin")
    #expect(client.executable.path == "/opt/homebrew/bin/uv")
    #expect(client.arguments == ["run", "--project", "/Users/me/stickler", "stickler-bridge"])
    #expect(client.directory == folder)
    #expect(client.environment == [
        "STICKLER_PACKAGED": "macos",
        "STICKLER_ADAPTER_SOURCES": "/Users/me/stickler/adapters",
        "LANGUAGE": "de-DE:en",
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
    ])
}

@Test func theCoreFindsUVAndHomebrewsToolsWhenTheAppWasStartedFromTheFinder() {
    // the Finder's PATH on the owner's Mac (2026-11-19): neither ~/.local/bin nor Homebrew
    let finder = "/usr/local/bin:/System/Cryptexes/App/usr/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    let path = CoreClient.toolPath(
        uv: URL(fileURLWithPath: "/Users/me/.local/bin/uv"), inherited: finder)
    #expect(path.split(separator: ":").map(String.init) == [
        "/Users/me/.local/bin", "/opt/homebrew/bin", "/usr/local/bin",
        "/System/Cryptexes/App/usr/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"
    ])
    #expect(CoreClient.toolPath(uv: URL(fileURLWithPath: "/a/uv"), inherited: "")
        == "/a:/opt/homebrew/bin:/usr/local/bin")
}

@Test func aPathForTheCoreReplacesTheAppsOwn() async {
    let wanted = "/somewhere/bin:" + (ProcessInfo.processInfo.environment["PATH"] ?? "")
    let code = """
        import json, os
        line = {"event": "notice", "seq": 1, "text": os.environ["PATH"], "opens": None}
        print(json.dumps(line), flush=True)
        """
    let client = CoreClient(
        executable: URL(fileURLWithPath: "/usr/bin/env"), arguments: ["python3", "-c", code],
        environment: ["PATH": wanted])
    let seen = Recorder()
    seen.start(client)
    #expect(await eventually(10) { !seen.events.isEmpty })
    #expect(seen.events.first == .event(seq: 1, .notice(Notice(text: wanted, opens: nil))))
}

@Test(.timeLimit(.minutes(1))) func quittingACoreThatNeitherAnswersNorStopsIsBounded() async {
    // a core stuck in a command: it reads nothing, ignores SIGTERM, and never answers
    let client = fakeCore("""
        import signal, time
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        print('{"event": "hello", "protocol": 1, "version": "8", "language": "en"}', flush=True)
        time.sleep(60)
        """)
    let seen = Recorder()
    seen.start(client)
    #expect(await eventually(10) { !seen.events.isEmpty })
    let start = Date()
    await client.quit(seconds: 1)
    #expect(Date().timeIntervalSince(start) < 5)
    #expect(!client.isRunning)
    #expect(await eventually(5) { seen.ended?.reason == .signalled(SIGKILL) })
}

@Test(.timeLimit(.minutes(1))) func aCancelledSendGivesUpWaiting() async throws {
    let client = fakeCore("import time; time.sleep(30)")  // reads nothing, answers nothing
    let seen = Recorder()
    seen.start(client)
    let waiting = Task { try await client.send(.start) }
    try await Task.sleep(for: .milliseconds(200))
    waiting.cancel()
    await #expect(throws: CancellationError.self) { try await waiting.value }
    client.terminate()
    #expect(await eventually(10) { seen.ended != nil })
}
