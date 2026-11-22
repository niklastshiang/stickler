import Foundation
import Testing

@testable import SticklerCore

/// A core for a made-up bundle: it says `hello` and reads commands until `quit`.
let patientCore = """
    #!/bin/sh
    printf '%s\\n' '{"event": "hello", "protocol": 1, "version": "8", "language": "en"}'
    while read -r line; do
        case "$line" in *quit*) exit 0 ;; esac
    done

    """

@MainActor @Suite struct TheStart {
    @Test func beforeTheLaunchThereIsNoCore() throws {
        let harness = try Harness()
        let model = harness.model()
        #expect(model.phase == .launching)
        #expect(harness.cores.isEmpty)
        #expect(model.title == "Stickler" && model.subtitle.isEmpty)
    }

    @Test func theLaunchStartsTheCoreInTheReadersLanguages() async throws {
        let harness = try Harness()
        let model = harness.model()
        model.launch()
        #expect(model.phase == .running)
        #expect(harness.languages == [["de-DE", "en"]])
        #expect(await settled { harness.core.actions == [.start] })
    }

    @Test func theFolderAnEarlierBuildAskedForIsForgotten() throws {
        // builds before the app brought its core asked "Where Is Stickler?" and kept the answer
        let harness = try Harness()
        harness.defaults.set("/Users/me/stickler", forKey: "SticklerFolder")
        let model = harness.model()
        #expect(AppModel.formerFolderKey == "SticklerFolder")
        model.launch()
        #expect(harness.defaults.object(forKey: "SticklerFolder") == nil)
        #expect(model.phase == .running)  // and nothing is asked
        #expect(harness.cores.count == 1)
    }

    /// A model over the real client for the made-up app at `resources`.
    func model(_ harness: Harness, resources: URL) -> AppModel {
        AppModel(defaults: harness.defaults, languages: ["en"]) { languages in
            CoreClient.app(
                languages: languages, environment: [:], resources: resources, development: false)
        }
    }

    @Test func anAppWithoutItsCoreStopsAndSaysWhatIsMissing() async throws {
        let bare = FileManager.default.temporaryDirectory
            .appendingPathComponent("stickler-bare-\(UUID().uuidString)")
        let model = model(try Harness(), resources: bare)
        model.launch()
        #expect(await settled { model.phase != .running })
        guard case .stopped(let end) = model.phase else {
            Issue.record("not stopped: \(model.phase)")
            return
        }
        #expect(end.reason == .notStarted("parts of it are missing"))
        #expect(end.neverStarted)  // the page shows the details unfolded
        #expect(end.details.count == 5)  // Python, uv, ffmpeg, ffprobe and the adapters
        #expect(end.details.first == "missing: \(bare.path)/core/python/bin/python3")
        #expect(end.details.last == "missing: \(bare.path)/core/python/share/stickler/adapters")
        #expect(model.notice == nil)  // the page says it; `start` going nowhere is no notice
        model.startAgain()
        #expect(await settled { model.phase == .stopped(end) })  // still not there
    }

    @Test(.timeLimit(.minutes(1))) func startAgainRunsTheCoreOnceTheBundleIsWhole() async throws {
        let resources = try madeUpBundle(python: patientCore, without: ["bin/ffprobe"])
        let ffprobe = resources.appendingPathComponent("core/bin/ffprobe")
        let model = model(try Harness(), resources: resources)
        model.launch()
        #expect(await settled { model.phase != .running })
        #expect(model.phase == .stopped(CoreEnd(
            reason: .notStarted("parts of it are missing"),
            details: ["missing: \(ffprobe.path)"])))
        try Data("#!/bin/sh\n".utf8).write(to: ffprobe)
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o755], ofItemAtPath: ffprobe.path)
        model.startAgain()
        #expect(await settled(tries: 2000) { model.language == "en" })  // its hello came
        #expect(model.phase == .running)
        await model.quit()
        #expect(model.phase == .running)  // quitting shows no page
    }
}

@MainActor @Suite struct WhatTheCoreSays {
    @Test func eventsBecomeTheStateTheListAndTheNotice() async throws {
        let harness = try Harness()
        let model = harness.model()
        model.launch()
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
        model.launch()
        try harness.core.emit(#"{"event": "state", "seq": 5, "state": \#(analysing)}"#)
        try harness.core.emit(#"{"event": "state", "seq": 4, "state": \#(emptyState)}"#)
        try harness.core.emit(#"{"event": "notice", "seq": 6, "text": "done", "opens": null}"#)
        #expect(await settled { model.notice != nil })
        #expect(model.state.screen.kind == "analysing")
    }

    @Test func aStoppedCoreShowsItsEndAndStartAgainStartsANewOne() async throws {
        let harness = try Harness()
        let model = harness.model()
        model.launch()
        let first = harness.core
        try first.emit(#"{"event": "state", "seq": 1, "state": \#(analysing)}"#)
        let end = CoreEnd(reason: .signalled(9), details: ["Killed"])
        first.stop(end)
        #expect(await settled { model.phase == .stopped(end) })
        model.open("/m/b.flac")  // nobody to send it to
        #expect(first.actions == [.start])

        model.startAgain()
        #expect(model.phase == .running && harness.cores.count == 2)
        #expect(first.quitWith == nil)  // a core that ended by itself is not asked to quit
        #expect(model.state == .empty)  // the new core's state comes from the core
        try first.emit(#"{"event": "notice", "seq": 2, "text": "old", "opens": null}"#)
        try harness.core.emit(#"{"event": "notice", "seq": 1, "text": "new", "opens": null}"#)
        #expect(await settled { model.notice != nil })
        #expect(model.notice?.text == "new")
        #expect(await settled { harness.core.actions == [.start] })
    }

    @Test func aCoreStillRunningIsToldToQuitWhenTheNextOneStarts() async throws {
        // two cores would share the same settings, recent songs and cache; the old one is
        // let go at once and ends in the background
        let harness = try Harness()
        let model = harness.model()
        model.launch()
        let first = harness.core
        model.startAgain()
        #expect(harness.cores.count == 2 && model.phase == .running)
        #expect(await settled { first.quitWith == 3 })
        try first.emit(#"{"event": "state", "seq": 1, "state": \#(analysing)}"#)
        first.stop(CoreEnd(reason: .exited(0), details: []))  // its end is not the new core's
        try await Task.sleep(for: .milliseconds(50))
        #expect(model.phase == .running)
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

    @Test func quittingEndsTheCorePolitely() async throws {
        let harness = try Harness()
        let model = harness.model()
        model.launch()
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
        model.launch()
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
        model.backUp(to: "/d/b.zip")
        model.restore(from: "/d/b.zip")
        let expected: [Command] = [
            .start, .open(path: "/m/a.flac"), .cancel, .retry, .close, .agree, .notNow,
            .retrySetup, .forgetRecent(path: "/m/gone.flac"),
            .exportMusicXML(dest: "/d/a.musicxml"),
            .exportDrumTrack(dest: "/d/a.flac"), .removeModels(everything: true),
            .backUp(dest: "/d/b.zip"), .restore(src: "/d/b.zip")
        ]
        #expect(await settled { harness.core.actions.count == expected.count })
        #expect(harness.core.actions == expected)  // in the order the reader gave them
    }

    @Test func aRefusedCommandSaysWhyAndAStoppedCoreSaysNothing() async throws {
        let harness = try Harness()
        let model = harness.model()
        model.launch()
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
        model.launch()
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
        harness.core.answer(
            "backup_summary",
            with: #""ok": true, "created": "2026-11-22", "songs": 2, "size": 9, "text": "Made""#)
        let summary = BackupSummary(created: "2026-11-22", songs: 2, size: 9, text: "Made")
        #expect(await model.backupSummary(of: "/d/b.zip") == summary)

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
        #expect(model.phase == .launching)
    }
}
