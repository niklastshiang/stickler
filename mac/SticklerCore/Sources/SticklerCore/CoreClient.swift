import Foundation

#if canImport(Glibc)
import Glibc
#endif

/// How the core ended (`CoreClient.onEnd`): for the page "Stickler Stopped Unexpectedly".
public struct CoreEnd: Equatable, Sendable {
    public enum Reason: Equatable, Sendable {
        /// The process exited with this status (0 after `quit`).
        case exited(Int32)
        /// A signal ended it (a crash, or `kill`).
        case signalled(Int32)
        /// Its `hello` named another protocol version: app and core are from different releases.
        case wrongProtocol(Int)
        /// It could not be started at all (no `uv`, a wrong folder).
        case notStarted(String)
    }

    public var reason: Reason
    /// The last lines the core wrote to stderr, then the last lines it sent that could not be
    /// read.
    public var details: [String]

    public init(reason: Reason, details: [String]) {
        self.reason = reason
        self.details = details
    }

    /// One line on how it ended, for "Technical Details" (not translated, as the rest there).
    public var summary: String {
        switch reason {
        case .exited(let status):
            "The core exited with status \(status)."
        case .signalled(let signal):
            "The core was ended by signal \(signal)."
        case .wrongProtocol(let version):
            "The core speaks protocol \(version); this app speaks \(BridgeProtocol.version)."
        case .notStarted(let why):
            "The core could not be started: \(why)"
        }
    }

    /// The summary and the details, as "Technical Details" shows them.
    public var technicalDetails: String {
        ([summary] + details).joined(separator: "\n")
    }
}

/// Errors of `CoreClient.send`.
public enum CoreClientError: Error, Equatable {
    /// The core is not running (not started yet, or ended before the reply came).
    case notRunning
    /// The core answered with an error reply.
    case refused(BridgeError)
}

/// The core as a subprocess speaking JSON lines (`docs/bridge.md`). It reads the core's stdout
/// and stderr on threads of its own, hands every event to `onEvent` in the order the core sent
/// them, answers each `send` with its reply, and calls `onEnd` once when the core is gone,
/// after its last event.
public final class CoreClient: @unchecked Sendable {
    public static let detailLines = 40

    /// A write to a core that has just died must be an error (`notRunning`), not SIGPIPE,
    /// whose default ends the whole app.
    private static let ignoreBrokenPipes: Void = {
        signal(SIGPIPE, SIG_IGN)
    }()

    public let executable: URL
    public let arguments: [String]
    public let directory: URL?
    public let environment: [String: String]

    // Everything below is guarded by `lock`.
    private let lock = NSLock()
    private let writing = NSLock()  // guards stdin's writes only, so a full pipe blocks no reader
    private var process: Process?
    private var input: FileHandle?
    private var nextID = 1
    private var waiting: [Int: CheckedContinuation<Reply, any Error>] = [:]
    private var stderrTail = Tail(limit: CoreClient.detailLines)
    private var unreadable: [String] = []  // the newest 5 lines that were not protocol
    private var openStreams = 0
    private var exit: CoreEnd.Reason?
    private var ended = false
    private var refusedProtocol: Int?
    private var onEvent: @Sendable (Incoming) -> Void = { _ in }
    private var onEnd: @Sendable (CoreEnd) -> Void = { _ in }

    /// `environment` is added to this process's own.
    public init(
        executable: URL, arguments: [String], directory: URL? = nil,
        environment: [String: String] = [:]
    ) {
        _ = Self.ignoreBrokenPipes
        self.executable = executable
        self.arguments = arguments
        self.directory = directory
        self.environment = environment
    }

    /// Starts the core. `onEvent` gets `hello` and every event; `onEnd` comes once, also when
    /// the process cannot be started. Both are called on the client's threads.
    public func start(
        onEvent: @escaping @Sendable (Incoming) -> Void,
        onEnd: @escaping @Sendable (CoreEnd) -> Void
    ) {
        let process = Process()
        process.executableURL = executable
        process.arguments = arguments
        process.currentDirectoryURL = directory
        process.environment = ProcessInfo.processInfo.environment.merging(environment) { $1 }
        let stdin = Pipe(), stdout = Pipe(), stderr = Pipe()
        process.standardInput = stdin
        process.standardOutput = stdout
        process.standardError = stderr
        process.terminationHandler = { [weak self] done in
            let reason: CoreEnd.Reason = done.terminationReason == .uncaughtSignal
                ? .signalled(done.terminationStatus) : .exited(done.terminationStatus)
            self?.finished(exit: reason)
        }
        lock.withLock {
            self.onEvent = onEvent
            self.onEnd = onEnd
            self.process = process
            self.input = stdin.fileHandleForWriting
            self.openStreams = 2
        }
        do {
            try Self.spawn(process)
        } catch {
            lock.withLock {
                self.process = nil
                self.input = nil
                self.openStreams = 0
            }
            onEnd(CoreEnd(reason: .notStarted(error.localizedDescription), details: []))
            return
        }
        read(stdout.fileHandleForReading, name: "stickler-core-out") { [weak self] line in
            self?.received(line)
        } done: { [weak self] in
            self?.streamClosed()
        }
        read(stderr.fileHandleForReading, name: "stickler-core-err") { [weak self] line in
            self?.lock.withLock { self?.stderrTail.feed(line + Data("\n".utf8)) }
        } done: { [weak self] in
            self?.streamClosed()
        }
    }

    /// Sends `command` and waits for its reply. Throws `refused` for an error reply,
    /// `notRunning` when the core is not there or ends first, and `CancellationError` when the
    /// waiting task is cancelled (the reply, if it comes, is dropped).
    public func send(_ command: Command) async throws -> Reply {
        let id = lock.withLock {
            defer { nextID += 1 }
            return nextID
        }
        let line = try command.line(id: id) + Data("\n".utf8)
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                lock.lock()
                guard let input, !ended else {
                    lock.unlock()
                    continuation.resume(throwing: CoreClientError.notRunning)
                    return
                }
                if Task.isCancelled {
                    lock.unlock()
                    continuation.resume(throwing: CancellationError())
                    return
                }
                waiting[id] = continuation
                lock.unlock()
                do {
                    // one writer at a time: a long line must not interleave with another
                    try writing.withLock { try input.write(contentsOf: line) }
                } catch {
                    lock.withLock { waiting.removeValue(forKey: id) }?
                        .resume(throwing: CoreClientError.notRunning)
                }
            }
        } onCancel: {
            lock.withLock { waiting.removeValue(forKey: id) }?
                .resume(throwing: CancellationError())
        }
    }

    /// Ends the core politely within `seconds`: `quit`, then stdin closed; still running at
    /// the deadline, it gets SIGTERM, and a second later SIGKILL. Returns once it is gone.
    public func quit(seconds: Double = 3) async {
        let deadline = Date().addingTimeInterval(seconds)
        _ = try? await withTimeout(seconds) { try await self.send(.quit) }
        lock.withLock {
            try? input?.close()
            input = nil
        }
        await waitForExit(until: deadline)
        if isRunning {
            terminate()
            await waitForExit(until: Date().addingTimeInterval(1))
        }
        if let pid = processIdentifier {
            kill(pid, SIGKILL)
            await waitForExit(until: Date().addingTimeInterval(2))
        }
    }

    private func waitForExit(until deadline: Date) async {
        while isRunning, Date() < deadline {
            try? await Task.sleep(for: .milliseconds(20))
        }
    }

    /// Ends the core at once (SIGTERM).
    public func terminate() {
        lock.withLock { process }?.terminate()
    }

    public var isRunning: Bool {
        lock.withLock { process?.isRunning ?? false }
    }

    /// The core's process id, while it runs.
    public var processIdentifier: Int32? {
        lock.withLock { process?.isRunning == true ? process?.processIdentifier : nil }
    }

    /// Starts `process` from a thread whose signal mask is empty. The child inherits the mask
    /// of the thread that starts it, Foundation on Linux does not reset it, and the threads of
    /// Swift's concurrency pool block signals: a core started from one would ignore SIGTERM
    /// (`terminate`, uv passing it on) and hand that mask to the models it runs.
    private static func spawn(_ process: Process) throws {
        let outcome = SpawnOutcome()
        let thread = Thread {
            var none = sigset_t()
            sigemptyset(&none)
            pthread_sigmask(SIG_SETMASK, &none, nil)
            do {
                try process.run()
            } catch {
                outcome.failure = error
            }
            outcome.done.signal()
        }
        thread.name = "stickler-core-start"
        thread.start()
        outcome.done.wait()
        if let failure = outcome.failure {
            throw failure
        }
    }

    // reading

    private func read(
        _ handle: FileHandle, name: String, line: @escaping @Sendable (Data) -> Void,
        done: @escaping @Sendable () -> Void
    ) {
        let thread = Thread {
            var splitter = LineSplitter()
            // `availableData` returns what has arrived; `read(upToCount:)` waits for the whole
            // count on Linux, so a short line would sit there until more comes.
            while case let chunk = handle.availableData, !chunk.isEmpty {
                splitter.feed(chunk).forEach(line)
            }
            splitter.finish().map(line)
            done()
        }
        thread.name = name
        thread.start()
    }

    private func received(_ line: Data) {
        let incoming: Incoming
        do {
            incoming = try Incoming(line: line)
        } catch {
            lock.withLock {
                unreadable = (unreadable + ["unreadable line from the core: \(describe(line))"])
                    .suffix(5)
            }
            return
        }
        switch incoming {
        case .reply(let reply):
            let waiter = lock.withLock { reply.id.flatMap { waiting.removeValue(forKey: $0) } }
            if let error = reply.error {
                waiter?.resume(throwing: CoreClientError.refused(error))
            } else {
                waiter?.resume(returning: reply)
            }
        case .hello(let hello) where !BridgeProtocol.speaks(hello.protocol):
            lock.withLock { refusedProtocol = hello.protocol }
            terminate()
        default:
            let deliver = lock.withLock { onEvent }
            deliver(incoming)
        }
    }

    private func describe(_ line: Data) -> String {
        let text = String(bytes: line.prefix(200), encoding: .utf8) ?? "(not UTF-8)"
        return line.count > 200 ? text + "…" : text
    }

    // the end: after the exit and both streams' last lines, once

    private func streamClosed() {
        lock.withLock { openStreams -= 1 }
        endIfDone()
    }

    private func finished(exit reason: CoreEnd.Reason) {
        lock.withLock { exit = reason }
        endIfDone()
    }

    private func endIfDone() {
        lock.lock()
        guard !ended, let exit, openStreams == 0 else {
            lock.unlock()
            return
        }
        ended = true
        stderrTail.finish()
        let end = CoreEnd(
            reason: refusedProtocol.map { .wrongProtocol($0) } ?? exit,
            details: stderrTail.lines + unreadable)
        let left = waiting.values
        waiting = [:]
        input = nil
        let notify = onEnd
        lock.unlock()
        left.forEach { $0.resume(throwing: CoreClientError.notRunning) }
        notify(end)
    }
}

/// What the starting thread hands back (written before `done` is signalled, read after).
private final class SpawnOutcome: @unchecked Sendable {
    let done = DispatchSemaphore(value: 0)
    var failure: (any Error)?
}

/// Runs `work`, giving up after `seconds`.
func withTimeout<T: Sendable>(
    _ seconds: Double, _ work: @escaping @Sendable () async throws -> T
) async throws -> T {
    try await withThrowingTaskGroup(of: T.self) { group in
        group.addTask { try await work() }
        group.addTask {
            try await Task.sleep(for: .seconds(seconds))
            throw CancellationError()
        }
        defer { group.cancelAll() }
        guard let first = try await group.next() else { throw CancellationError() }
        return first
    }
}

extension CoreClient {
    /// The core of the Mac app: `uv run stickler-bridge` in the Stickler folder, as an
    /// installed app (`STICKLER_PACKAGED=macos`: its files under ~/Library, its models set up
    /// from the folder's adapters). `languages` are the user's, best first; `path` is this
    /// process's `PATH`, which the core's starts from (`toolPath`).
    public static func bridge(
        in folder: URL, uv tool: URL, languages: [String],
        path: String = ProcessInfo.processInfo.environment["PATH"] ?? ""
    ) -> CoreClient {
        CoreClient(
            executable: tool, arguments: ["run", "--project", folder.path, "stickler-bridge"],
            directory: folder,
            environment: [
                "STICKLER_PACKAGED": "macos",
                "STICKLER_ADAPTER_SOURCES": folder.appendingPathComponent("adapters").path,
                "LANGUAGE": languages.joined(separator: ":"),
                "PATH": toolPath(uv: tool, inherited: path)
            ])
    }

    /// The core's `PATH`: the folder of the `uv` that was found (the core calls `uv` itself
    /// for the models), Homebrew's two prefixes (ffmpeg and ffprobe), then `inherited`, each
    /// folder once. An app started from the Finder inherits only the system's folders.
    public static func toolPath(uv tool: URL, inherited: String) -> String {
        let folders =
            [tool.deletingLastPathComponent().path, "/opt/homebrew/bin", "/usr/local/bin"]
            + inherited.split(separator: ":").map(String.init)
        var seen = Set<String>()
        return folders.filter { seen.insert($0).inserted }.joined(separator: ":")
    }
}
