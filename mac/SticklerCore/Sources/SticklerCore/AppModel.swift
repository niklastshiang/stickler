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

/// The window's model (SPEC.md, module `mac-shell`): the core's latest state, the recent
/// songs, the newest notice, and whether the core runs. It forwards every action as one
/// command and decides no flow itself; the core does.
@MainActor @Observable
public final class AppModel {
    public enum Phase: Equatable {
        /// Before `launch`: no core yet, and nothing to show.
        case launching
        case running
        /// The core ended or did not start (a part of the app is missing): the page
        /// "Stickler Stopped Unexpectedly".
        case stopped(CoreEnd)
    }

    public private(set) var phase: Phase = .launching
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
    /// The sheet music of the shown result (module `mac-sheet`).
    public let sheet: SheetModel
    /// Playing the shown result (SPEC.md "Mac playback").
    public let playback: PlaybackModel

    /// Where builds before `mac-package` kept the answer to "Where Is Stickler?".
    public static let formerFolderKey = "SticklerFolder"

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
    private let languages: [String]
    private let makeCore: @Sendable ([String]) -> any Core
    private var core: (any Core)?
    private var listener: Task<Void, Never>?
    private var outbox: AsyncStream<Command>.Continuation?  // commands, in the reader's order
    private var lastSeq = 0

    /// `settle`: how long the sheet's width must hold before its pages are asked for.
    /// `makeCore` builds a core for the reader's languages: the app's own (`CoreClient.app`).
    /// `player` plays the result (none: the controls stay off); `tick` is how often its
    /// position is read while it plays.
    public init(
        defaults: UserDefaults = .standard,
        languages: [String] = Locale.preferredLanguages,
        settle: Duration = .milliseconds(300),
        player: (any Playing)? = nil,
        tick: Duration = .milliseconds(50),
        makeCore: @escaping @Sendable ([String]) -> any Core = { CoreClient.app(languages: $0) }
    ) {
        self.defaults = defaults
        self.languages = languages
        self.makeCore = makeCore
        // the sheet's refusals show as the window's notice
        let tell = Refusals()
        sheet = SheetModel(settle: settle) { tell.model?.refused($0) }
        playback = PlaybackModel(player: player, tick: tick) { tell.model?.tell($0) }
        tell.model = self
    }

    /// Lets the sheet reach the model it belongs to, once that exists.
    @MainActor private final class Refusals {
        weak var model: AppModel?
    }

    // the core

    /// At launch: the app's core starts. The folder an earlier build asked for is forgotten.
    public func launch() {
        defaults.removeObject(forKey: Self.formerFolderKey)
        startCore(makeCore(languages))
    }

    /// "Start Again" on the stopped page: a new core.
    public func startAgain() {
        startCore(makeCore(languages))
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
        sheet.attach(nil)
        playback.attach(nil)
        defer { core = nil }
        return core
    }

    private enum Signal: Sendable {
        case incoming(Incoming)
        case ended(CoreEnd)
    }

    private func startCore(_ next: any Core) {
        // a core still running is let go and told to quit, politely and in the background:
        // two cores would share the same settings, recent songs and cache
        if let old = letGo() {
            Task { await old.quit(seconds: 3) }
        }
        core = next
        state = .empty
        lastSeq = 0
        notice = nil
        phase = .running
        sheet.attach(next)
        playback.attach(next)
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
            case .state(let next):
                state = next
                sheet.show(next.screen)
                playback.show(next.screen)
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
    public func backUp(to path: String) { send(.backUp(dest: path)) }
    public func restore(from path: String) { send(.restore(src: path)) }
    /// One change from the corrections inspector (SPEC.md "Mac corrections"); the core shows
    /// it at once and writes the notes once the changes pause.
    public func correct(_ change: Correction) { send(.correct(change)) }

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

    /// What a backup holds and the restore's question; nil (with the core's reason as the
    /// notice) when the file is no backup.
    public func backupSummary(of path: String) async -> BackupSummary? {
        await ask(.backupSummary(src: path), BackupSummary.self)
    }

    /// What "Uninstall Stickler…" frees, for its dialog.
    public func uninstallSizes() async -> UninstallSizes? {
        await ask(.uninstallSizes, UninstallSizes.self)
    }

    /// Removes Stickler's folders through the core; true once they are gone (the core replies
    /// after it removed them), false when it refused (with its reason as the notice).
    public func uninstall(everything: Bool) async -> Bool {
        await ask(.uninstall(everything: everything), Done.self) != nil
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
