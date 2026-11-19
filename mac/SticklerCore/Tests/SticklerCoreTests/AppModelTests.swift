import Foundation
import Testing

@testable import SticklerCore

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
        #expect(await settled { harness.core.actions == [.start] })

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
        #expect(first.actions == [.start])

        model.startAgain()
        #expect(model.phase == .running && harness.cores.count == 2)
        #expect(model.state == .empty)  // the new core's state comes from the core
        try first.emit(#"{"event": "notice", "seq": 2, "text": "old", "opens": null}"#)
        try harness.core.emit(#"{"event": "notice", "seq": 1, "text": "new", "opens": null}"#)
        #expect(await settled { model.notice != nil })
        #expect(model.notice?.text == "new")
        #expect(await settled { harness.core.actions == [.start] })
    }

    @Test func anotherFolderEndsTheRunningCoreFirst() async throws {
        let harness = try Harness()
        let model = harness.model()
        model.choose(folder: harness.folder)
        let first = harness.core
        model.choose(folder: harness.folder)
        #expect(harness.cores.count == 2 && model.phase == .running)
        #expect(await settled { first.quitWith == 3 })
        first.stop(CoreEnd(reason: .exited(0), details: []))  // its end is not the new core's
        try await Task.sleep(for: .milliseconds(50))
        #expect(model.phase == .running)
    }

    @Test func aFolderThatCannotRunEndsTheRunningCoreToo() async throws {
        let harness = try Harness()
        let model = harness.model()
        model.choose(folder: harness.folder)
        let first = harness.core
        let elsewhere = harness.folder.deletingLastPathComponent()
        model.choose(folder: elsewhere)
        #expect(model.phase == .needsFolder(.notStickler(elsewhere.path)))
        #expect(await settled { first.quitWith == 3 })
        try first.emit(#"{"event": "state", "seq": 1, "state": \#(analysing)}"#)
        try await Task.sleep(for: .milliseconds(50))
        #expect(model.state == .empty)  // a core that was let go is not listened to
    }

    @Test func eachNoticeCountsEvenWhenItSaysTheSame() throws {
        let model = try Harness().model()
        let saved = Notice(text: "Saved “a.pdf”", opens: "/d/a.pdf")
        model.tell(saved)
        let first = model.noticeSerial
        model.tell(saved)
        #expect(model.noticeSerial == first + 1)
    }

    @Test func startAgainWithoutAFolderAsksForOne() throws {
        let harness = try Harness()
        let model = harness.model()
        model.startAgain()
        #expect(model.phase == .needsFolder(nil))
    }

    @Test func anAppWithItsOwnCoreStartsItAndNeverAsksForAFolder() async throws {
        let harness = try Harness()
        let core = URL(fileURLWithPath: "/Stickler.app/Contents/Resources/core")
        let model = harness.model(bundled: core)
        model.launch()
        #expect(model.phase == .running)
        #expect(harness.bundledCalls == [core])
        #expect(harness.calls.isEmpty)  // no folder, no uv of the Mac's
        harness.core.stop(CoreEnd(reason: .exited(1), details: []))
        #expect(await settled { model.phase != .running })
        model.startAgain()
        #expect(model.phase == .running)
        #expect(harness.bundledCalls == [core, core])
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
        #expect(await settled { harness.core.actions.count == expected.count })
        #expect(harness.core.actions == expected)  // in the order the reader gave them
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
