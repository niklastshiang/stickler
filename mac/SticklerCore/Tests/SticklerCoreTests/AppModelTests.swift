import Foundation
import Testing

@testable import SticklerCore

/// A core that records the commands and answers as told; the test sends its events.
final class FakeCore: Core, @unchecked Sendable {
    private let lock = NSLock()
    private var commands: [Command] = []
    private var answers: [String: String] = [:]  // command name → reply line without id
    private var event: (@Sendable (Incoming) -> Void)?
    private var end: (@Sendable (CoreEnd) -> Void)?
    private(set) var quitWith: Double?

    var sent: [Command] { lock.withLock { commands } }

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

    func send(_ command: Command) async throws -> Reply {
        let fields = lock.withLock {
            commands.append(command)
            return answers[command.name] ?? #""ok": true"#
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
    }

    var cores: [FakeCore] { made.lock.withLock { made.cores } }
    var calls: [Call] { made.lock.withLock { made.calls } }
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

    func model(uvPlaces: [URL]? = nil) -> AppModel {
        let made = made
        return AppModel(
            defaults: defaults,
            uvPlaces: uvPlaces ?? [URL(fileURLWithPath: "/nonexistent/uv"), uv],
            languages: ["de-DE", "en"]
        ) { folder, tool, languages in
            let core = FakeCore()
            made.lock.withLock {
                made.cores.append(core)
                made.calls.append(Call(folder: folder, tool: tool, languages: languages))
            }
            return core
        }
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

@MainActor @Suite struct TheFolder {
    @Test func withoutARememberedFolderTheModelAsksForIt() throws {
        let harness = try Harness()
        let model = harness.model()
        model.launch()
        #expect(model.phase == .needsFolder(nil) && harness.cores.isEmpty)
    }

    @Test func aFolderThatIsNotSticklerIsRefusedAndNotRemembered() throws {
        let harness = try Harness(stickler: false)
        let model = harness.model()
        model.choose(folder: harness.folder)
        #expect(model.phase == .needsFolder(.notStickler(harness.folder.path)))
        #expect(harness.defaults.string(forKey: AppModel.folderKey) == nil)
        #expect(AppModel.problem(with: harness.folder.appendingPathComponent("pyproject.toml"))
                != nil)
    }

    @Test func withoutUVTheCoreCannotStart() throws {
        let harness = try Harness()
        let model = harness.model(uvPlaces: [URL(fileURLWithPath: "/nonexistent/uv")])
        model.choose(folder: harness.folder)
        #expect(model.phase == .needsFolder(.noUV) && harness.cores.isEmpty)
    }

    @Test func aChosenFolderIsRememberedAndItsCoreStarts() async throws {
        let harness = try Harness()
        let model = harness.model()
        model.choose(folder: harness.folder)
        #expect(model.phase == .running && model.folder == harness.folder)
        #expect(harness.defaults.string(forKey: AppModel.folderKey) == harness.folder.path)
        let call = try #require(harness.calls.first)
        #expect(call.folder == harness.folder && call.tool == harness.uv)
        #expect(call.languages == ["de-DE", "en"])
        #expect(await settled { harness.core.sent == [.start] })

        let again = harness.model()  // the next launch
        again.launch()
        #expect(again.phase == .running && harness.cores.count == 2)
    }

    @Test func theUVPlacesStartWithTheInstallerAndHomebrewThenPath() {
        let places = AppModel.defaultUVPlaces(environment: ["PATH": "/a/bin:/b/bin"]).map(\.path)
        #expect(places.first?.hasSuffix("/.local/bin/uv") == true)
        #expect(Array(places.dropFirst()) == [
            "/opt/homebrew/bin/uv", "/usr/local/bin/uv", "/a/bin/uv", "/b/bin/uv"
        ])
    }
}

@MainActor @Suite struct WhatTheCoreSays {
    @Test func eventsBecomeTheStateTheListAndTheNotice() async throws {
        let harness = try Harness()
        let model = harness.model()
        model.choose(folder: harness.folder)
        let core = harness.core
        try core.emit(#"{"event": "hello", "protocol": 1, "version": "7", "language": "de"}"#)
        try core.emit(#"{"event": "state", "seq": 1, "state": \#(analysing)}"#)
        let row = #"{"path": "/m/a.flac", "title": "A", "detail": "today", "missing": false}"#
        try core.emit(#"{"event": "recent", "seq": 2, "rows": [\#(row)]}"#)
        try core.emit(#"{"event": "notice", "seq": 3, "text": "Saved", "opens": "/m/a.musicxml"}"#)
        try core.emit(#"{"event": "progress", "seq": 4}"#)
        #expect(await settled { model.notice != nil })
        #expect(model.language == "de")
        #expect(model.state.screen.kind == "analysing" && model.state.can.cancel)
        #expect(model.recent.map(\.title) == ["A"])
        #expect(model.notice == Notice(text: "Saved", opens: "/m/a.musicxml"))
        model.dismissNotice()
        #expect(model.notice == nil)
    }

    @Test func aLateEventIsDropped() async throws {
        let harness = try Harness()
        let model = harness.model()
        model.choose(folder: harness.folder)
        try harness.core.emit(#"{"event": "state", "seq": 5, "state": \#(analysing)}"#)
        try harness.core.emit(#"{"event": "state", "seq": 4, "state": \#(emptyState)}"#)
        try harness.core.emit(#"{"event": "notice", "seq": 6, "text": "done", "opens": null}"#)
        #expect(await settled { model.notice != nil })
        #expect(model.state.screen.kind == "analysing")
    }

    @Test func aStoppedCoreShowsItsEndAndStartAgainStartsANewOne() async throws {
        let harness = try Harness()
        let model = harness.model()
        model.choose(folder: harness.folder)
        let first = harness.core
        try first.emit(#"{"event": "state", "seq": 1, "state": \#(analysing)}"#)
        let end = CoreEnd(reason: .signalled(9), details: ["Killed"])
        first.stop(end)
        #expect(await settled { model.phase == .stopped(end) })
        model.open("/m/b.flac")  // nobody to send it to
        #expect(first.sent == [.start])

        model.startAgain()
        #expect(model.phase == .running && harness.cores.count == 2)
        #expect(model.state == .empty)  // the new core's state comes from the core
        try first.emit(#"{"event": "notice", "seq": 2, "text": "old", "opens": null}"#)
        try harness.core.emit(#"{"event": "notice", "seq": 1, "text": "new", "opens": null}"#)
        #expect(await settled { model.notice != nil })
        #expect(model.notice?.text == "new")
        #expect(await settled { harness.core.sent == [.start] })
    }

    @Test func startAgainWithoutAFolderAsksForOne() throws {
        let harness = try Harness()
        let model = harness.model()
        model.startAgain()
        #expect(model.phase == .needsFolder(nil))
    }

    @Test func quittingEndsTheCorePolitely() async throws {
        let harness = try Harness()
        let model = harness.model()
        model.choose(folder: harness.folder)
        await model.quit()
        #expect(harness.core.quitWith == 3)
    }
}

/// A `not_now` reply's fields with `message`.
func refusal(_ message: String) -> String {
    #""ok": false, "error": {"code": "not_now", "message": "\#(message)"}"#
}

@MainActor @Suite struct WhatTheReaderDoes {
    @Test func eachActionSendsItsOneCommand() async throws {
        let harness = try Harness()
        let model = harness.model()
        model.choose(folder: harness.folder)
        model.open("/m/a.flac")
        model.cancel()
        model.retry()
        model.close()
        model.agree()
        model.notNow()
        model.retrySetup()
        model.forget("/m/gone.flac")
        model.exportMusicXML(to: "/d/a.musicxml")
        model.exportDrumTrack(to: "/d/a.flac")
        model.removeModels(everything: true)
        let expected: [Command] = [
            .start, .open(path: "/m/a.flac"), .cancel, .retry, .close, .agree, .notNow,
            .retrySetup, .forgetRecent(path: "/m/gone.flac"),
            .exportMusicXML(dest: "/d/a.musicxml"),
            .exportDrumTrack(dest: "/d/a.flac"), .removeModels(everything: true)
        ]
        #expect(await settled { harness.core.sent.count == expected.count })
        // each in its own task: the order is the scheduler's, the commands are exact
        let sent = harness.core.sent
        #expect(expected.allSatisfy { command in sent.contains(command) }, "\(sent)")
    }

    @Test func aRefusedCommandSaysWhyAndAStoppedCoreSaysNothing() async throws {
        let harness = try Harness()
        let model = harness.model()
        model.choose(folder: harness.folder)
        harness.core.answer("retry", with: refusal("Nicht jetzt."))
        harness.core.answer("cancel", with: "not running")
        model.cancel()
        model.retry()
        #expect(await settled { model.notice != nil })
        #expect(model.notice == Notice(text: "Nicht jetzt.", opens: nil))
    }

    @Test func questionsReturnTheirAnswers() async throws {
        let harness = try Harness()
        let model = harness.model()
        model.choose(folder: harness.folder)
        harness.core.answer(
            "drum_track_cost",
            with: #""ok": true, "minutes": 8, "text": "8 min", "download": true"#)
        harness.core.answer("a4_pages", with: #""ok": true, "title": "A", "pages": []"#)
        harness.core.answer(
            "removal_sizes",
            with: #""ok": true, "models": 2, "everything": 3, "models_text": "2 B", "#
                + #""everything_text": "3 B""#)
        let cost = await model.drumTrackCost()
        #expect(cost == DrumTrackCost(minutes: 8, text: "8 min", download: true))
        #expect(await model.a4Pages() == A4Pages(title: "A", pages: []))
        #expect(await model.removalSizes()?.everythingText == "3 B")

        harness.core.answer("a4_pages", with: refusal("No result."))
        #expect(await model.a4Pages() == nil)
        #expect(model.notice?.text == "No result.")
    }

    @Test func theAppsOwnNoticeShowsLikeTheCores() throws {
        let model = try Harness().model()
        model.tell(Notice(text: "Saved “a.pdf”", opens: "/d/a.pdf"))
        #expect(model.notice == Notice(text: "Saved “a.pdf”", opens: "/d/a.pdf"))
    }

    @Test func withoutACoreQuestionsHaveNoAnswer() async throws {
        let model = try Harness().model()
        #expect(await model.drumTrackCost() == nil)
        model.open("/m/a.flac")  // nothing happens
        #expect(model.phase == .needsFolder(nil))
    }
}
