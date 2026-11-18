import Foundation
import Observation

/// What the app needs of the core (`CoreClient`; a fake in tests).
public protocol Core: AnyObject, Sendable {
    func start(
        onEvent: @escaping @Sendable (Incoming) -> Void,
        onEnd: @escaping @Sendable (CoreEnd) -> Void)
    func send(_ command: Command) async throws -> Reply
    func quit(seconds: Double) async
}

extension CoreClient: Core {}

/// Why a chosen folder cannot run the core.
public enum FolderProblem: Equatable, Sendable {
    /// It is not a Stickler checkout (no `pyproject.toml` and `adapters/`).
    case notStickler(String)
    /// `uv` was not found in any of the places a Mac app can see.
    case noUV
}

/// The window's model (SPEC.md, module `mac-shell`): the core's latest state, the recent
/// songs, the newest notice, and whether the core runs. It forwards every action as one
/// command and decides no flow itself; the core does.
@MainActor @Observable
public final class AppModel {
    public enum Phase: Equatable {
        /// The Stickler folder is not chosen yet, or cannot run the core.
        case needsFolder(FolderProblem?)
        case running
        /// The core ended or did not start: the page "Stickler Stopped Unexpectedly".
        case stopped(CoreEnd)
    }

    public private(set) var phase: Phase = .needsFolder(nil)
    public private(set) var state = AppState.empty
    public private(set) var recent: [RecentRow] = []
    /// The newest notice; the window shows it until it is dismissed or a newer one comes.
    public private(set) var notice: Notice? {
        didSet { noticeSerial += 1 }
    }
    /// Counts the notices, so a second one that says the same still restarts its timer.
    public private(set) var noticeSerial = 0
    /// The core's language (`hello`).
    public private(set) var language: String?
    public private(set) var folder: URL?

    public static let folderKey = "SticklerFolder"

    /// The window's title, as the GTK window's header: the song once it has one, else the app.
    public var title: String {
        switch state.screen {
        case .result(let result): result.title
        case .exporting(let exporting): exporting.title
        case .analysing(let analysing): analysing.name
        case .failed(let failure): failure.name
        default: "Stickler"
        }
    }

    /// The line under the title: artist, tempo and time signature of a result.
    public var subtitle: String {
        switch state.screen {
        case .result(let result): result.subtitle
        case .exporting(let exporting): exporting.subtitle
        default: ""
        }
    }

    private let defaults: UserDefaults
    private let uvPlaces: [URL]
    private let languages: [String]
    private let makeCore: @Sendable (URL, URL, [String]) -> any Core
    private var core: (any Core)?
    private var listener: Task<Void, Never>?
    private var outbox: AsyncStream<Command>.Continuation?  // commands, in the reader's order
    private var lastSeq = 0

    /// `uvPlaces`: where `uv` may be, first found wins (a Mac app started from the Finder
    /// has almost no PATH). `makeCore` builds the core for a folder, `uv` and languages.
    public init(
        defaults: UserDefaults = .standard,
        uvPlaces: [URL] = AppModel.defaultUVPlaces(),
        languages: [String] = Locale.preferredLanguages,
        makeCore: @escaping @Sendable (URL, URL, [String]) -> any Core = { folder, uv, languages in
            CoreClient.bridge(in: folder, uv: uv, languages: languages)
        }
    ) {
        self.defaults = defaults
        self.uvPlaces = uvPlaces
        self.languages = languages
        self.makeCore = makeCore
    }

    /// `~/.local/bin` (uv's installer), Homebrew's two prefixes, then PATH.
    public nonisolated static func defaultUVPlaces(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> [URL] {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let fixed = [
            home.appendingPathComponent(".local/bin/uv"),
            URL(fileURLWithPath: "/opt/homebrew/bin/uv"),
            URL(fileURLWithPath: "/usr/local/bin/uv")
        ]
        let path = (environment["PATH"] ?? "").split(separator: ":")
            .map { URL(fileURLWithPath: String($0)).appendingPathComponent("uv") }
        return fixed + path
    }

    // the core

    /// At launch: the remembered folder's core, or the question for the folder.
    public func launch() {
        guard let stored = defaults.string(forKey: Self.folderKey) else {
            phase = .needsFolder(nil)
            return
        }
        use(URL(fileURLWithPath: stored), remember: false)
    }

    /// The reader chose `url` (File › "Choose Stickler Folder…" or the first start).
    public func choose(folder url: URL) {
        use(url, remember: true)
    }

    /// "Start Again" on the stopped page.
    public func startAgain() {
        guard let folder else {
            phase = .needsFolder(nil)
            return
        }
        use(folder, remember: false)
    }

    /// Quitting: the core ends politely (at most 3 s, then it is terminated).
    public func quit() async {
        await letGo()?.quit(seconds: 3)
    }

    /// Stops listening to the current core and sending to it; returns it for ending.
    private func letGo() -> (any Core)? {
        listener?.cancel()
        listener = nil
        outbox?.finish()
        outbox = nil
        defer { core = nil }
        return core
    }

    private func use(_ url: URL, remember: Bool) {
        // a running core ends first, politely and in the background: two cores would share
        // the same settings, recent songs and cache
        if let old = letGo() {
            Task { await old.quit(seconds: 3) }
            state = .empty
        }
        if let problem = Self.problem(with: url) {
            phase = .needsFolder(problem)
            return
        }
        guard let uv = uvPlaces.first(where: {
            FileManager.default.isExecutableFile(atPath: $0.path)
        }) else {
            phase = .needsFolder(.noUV)
            return
        }
        if remember {
            defaults.set(url.path, forKey: Self.folderKey)
        }
        folder = url
        startCore(makeCore(url, uv, languages))
    }

    /// Whether `url` holds the core: a Stickler checkout has `pyproject.toml` and `adapters/`.
    public nonisolated static func problem(with url: URL) -> FolderProblem? {
        let files = FileManager.default
        var isFolder: ObjCBool = false
        let adapters = url.appendingPathComponent("adapters").path
        let ok = files.fileExists(atPath: url.appendingPathComponent("pyproject.toml").path)
            && files.fileExists(atPath: adapters, isDirectory: &isFolder) && isFolder.boolValue
        return ok ? nil : .notStickler(url.path)
    }

    private enum Signal: Sendable {
        case incoming(Incoming)
        case ended(CoreEnd)
    }

    private func startCore(_ next: any Core) {
        _ = letGo()
        core = next
        state = .empty
        lastSeq = 0
        notice = nil
        phase = .running
        // one stream keeps the core's order; separate tasks per event would not
        let (signals, feed) = AsyncStream<Signal>.makeStream()
        listener = Task { [weak self] in
            for await signal in signals {
                self?.handle(signal, from: next)
            }
        }
        // one sender keeps the reader's order; a task per command would not
        let (commands, post) = AsyncStream<Command>.makeStream()
        outbox = post
        Task { [weak self] in
            for await command in commands {
                do {
                    _ = try await next.send(command)
                } catch {
                    self?.refused(error)
                }
            }
        }
        next.start(
            onEvent: { feed.yield(.incoming($0)) },
            onEnd: {
                feed.yield(.ended($0))
                feed.finish()
            })
        send(.start)
    }

    private func handle(_ signal: Signal, from source: any Core) {
        guard source === core else { return }  // a core replaced by "Start Again"
        switch signal {
        case .incoming(.hello(let hello)):
            language = hello.language
        case .incoming(.event(let seq, let event)):
            guard seq > lastSeq else { return }  // a late event
            lastSeq = seq
            switch event {
            case .state(let next): state = next
            case .recent(let rows): recent = rows
            case .notice(let next): notice = next
            case .unknown: break
            }
        case .incoming(.reply):
            break  // replies go to their `send`
        case .ended(let end):
            _ = letGo()
            phase = .stopped(end)
        }
    }

    // what the reader does: one command each

    public func open(_ path: String) { send(.open(path: path)) }
    public func cancel() { send(.cancel) }
    public func retry() { send(.retry) }
    public func close() { send(.close) }
    public func agree() { send(.agree) }
    public func notNow() { send(.notNow) }
    public func retrySetup() { send(.retrySetup) }
    public func forget(_ path: String) { send(.forgetRecent(path: path)) }
    public func exportMusicXML(to path: String) { send(.exportMusicXML(dest: path)) }
    public func exportDrumTrack(to path: String) { send(.exportDrumTrack(dest: path)) }
    public func removeModels(everything: Bool) { send(.removeModels(everything: everything)) }

    /// File › Open Recent › Clear Menu: every recent song forgotten.
    public func clearRecent() {
        for row in recent {
            forget(row.path)
        }
    }

    /// A notice of the app's own (a PDF it wrote itself), shown like the core's.
    public func tell(_ notice: Notice) {
        self.notice = notice
    }

    public func dismissNotice() {
        notice = nil
    }

    /// What saving the drum track costs, for the alert before it starts.
    public func drumTrackCost() async -> DrumTrackCost? {
        await ask(.drumTrackCost, DrumTrackCost.self)
    }

    /// The PDF's pages and title.
    public func a4Pages() async -> A4Pages? {
        await ask(.a4Pages, A4Pages.self)
    }

    /// What "Remove Downloaded Models…" frees, for its dialog.
    public func removalSizes() async -> RemovalSizes? {
        await ask(.removalSizes, RemovalSizes.self)
    }

    private func send(_ command: Command) {
        outbox?.yield(command)
    }

    private func ask<T: Decodable & Sendable>(_ command: Command, _ type: T.Type) async -> T? {
        guard let core else { return nil }
        do {
            return try await core.send(command).payload(type)
        } catch {
            refused(error)
            return nil
        }
    }

    /// A refused command says why (translated by the core); a stopped core shows its page.
    private func refused(_ error: any Error) {
        if case CoreClientError.refused(let reason) = error {
            notice = Notice(text: reason.message, opens: nil)
        }
    }
}
