import SticklerCore
import WebKit
import XCTest

@testable import Stickler

/// The app's logic around AppKit's panels and alerts (task 117): `Exports`, `Removal`,
/// `Panels` and `PageLoad`, with the reader's answers given by `FakeAsking` and the core
/// played by `ScriptedCore`, so each flow is checked up to the command it sends.
@MainActor
final class LogicTests: XCTestCase {
    var asking = FakeAsking()
    var real: (any Asking)?

    override func setUp() async throws {
        real = Ask.reader
        asking = FakeAsking()
        Ask.reader = asking
    }

    override func tearDown() async throws {
        if let real {
            Ask.reader = real
        }
    }

    static let song = "/Users/me/Music/Eye of the Tiger.flac"

    /// A model showing the result of `song`, its core answering `replies` (ScriptedCore).
    func model(
        _ lines: [String] = [ScreenshotTests.result], replies: [String: String] = [:]
    ) async throws -> (AppModel, ScriptedCore) {
        let core = ScriptedCore(lines: lines, replies: replies)
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "logic-\(UUID().uuidString)"))
        let model = AppModel(defaults: defaults, languages: ["en"]) { _ in core }
        model.launch()
        let wantsResult = lines.contains(ScreenshotTests.result)
        try await until {
            guard model.phase == .running else { return false }
            if case .result = model.state.screen { return true }
            return !wantsResult
        }
        return (model, core)
    }

    /// Waits up to two seconds for `condition` (commands go out on tasks of their own).
    func until(_ condition: @escaping () -> Bool) async throws {
        var waited = 0
        while !condition(), waited < 200 {
            waited += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTAssertTrue(condition(), "timed out")
    }

    func temporary(_ name: String) -> URL {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("logic-\(UUID().uuidString)-\(name)")
    }

    // MARK: The View menu

    func testTheZoomItemsSendTheCoresCommandsWhileAResultIsShown() async throws {
        let size = #""ok": true, "zoom": 1.25, "percent": "125%""#
        let (model, core) = try await model(
            replies: ["zoom_in": size, "zoom_out": size, "actual_size": size])
        try await until { ZoomMenu.enabled(model) }
        XCTAssertEqual(ZoomMenu.items.map(\.title), ["Zoom In", "Zoom Out", "Actual Size"])
        XCTAssertEqual(ZoomMenu.items.map(\.key), ["+", "-", "0"])
        XCTAssertEqual(ZoomMenu.items.map(\.id), ZoomMenu.items.map(\.title))
        for (item, command) in zip(ZoomMenu.items, [Command.zoomIn, .zoomOut, .actualSize]) {
            item.act(model.sheet)
            try await until { core.sent.contains(command) }
        }
        try await until { model.sheet.percent == "125%" }
    }

    func testTheZoomItemsAreOffWithoutAResult() async throws {
        let (model, _) = try await model([ScreenshotTests.empty])
        XCTAssertFalse(ZoomMenu.enabled(model))
    }

    // MARK: Exports

    func testMusicXMLIsSavedWhereTheReaderSaysUnderTheCoresName() async throws {
        let (model, core) = try await model()
        let dest = temporary("eye.musicxml")
        asking.save = dest
        Exports.musicXML(model)
        try await until { core.sent.contains(.exportMusicXML(dest: dest.path)) }
        XCTAssertEqual(asking.offered, ["Eye of the Tiger.musicxml"])
    }

    func testACancelledSaveSendsNothing() async throws {
        let (model, core) = try await model()
        asking.save = nil
        Exports.musicXML(model)
        await Exports.pdf(model)
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertFalse(core.sent.contains { $0.name == "export_musicxml" || $0.name == "a4_pages" })
    }

    func testNothingIsExportedWithoutAResult() async throws {
        let (model, core) = try await model([ScreenshotTests.empty])
        asking.save = temporary("x")
        XCTAssertNil(Exports.result(model))
        Exports.musicXML(model)
        Exports.openWith(model)
        await Exports.drumTrack(model)
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertTrue(asking.offered.isEmpty && asking.opened.isEmpty)
        XCTAssertFalse(core.sent.contains { $0.name.hasPrefix("export") })
    }

    static let cost = #""ok": true, "minutes": 8, "text": "Takes about 8 minutes.", "#
        + #""download": true"#

    func testTheDrumTrackShowsItsCostFirstAndIsSavedWithItsName() async throws {
        let (model, core) = try await model(replies: ["drum_track_cost": Self.cost])
        let dest = temporary("drums.flac")
        asking.save = dest
        asking.goOn = true
        await Exports.drumTrack(model)
        XCTAssertEqual(asking.costs, ["Takes about 8 minutes."])
        XCTAssertEqual(asking.offered, ["Eye of the Tiger (drums).flac"])
        XCTAssertEqual(asking.endings, [["flac", "wav"]], "what the app's ffmpeg writes")
        try await until { core.sent.contains(.exportDrumTrack(dest: dest.path)) }
    }

    func testTheDrumTrackStopsWhenTheReaderDeclinesItsCost() async throws {
        let (model, core) = try await model(replies: ["drum_track_cost": Self.cost])
        asking.save = temporary("drums.flac")
        asking.goOn = false
        await Exports.drumTrack(model)
        XCTAssertTrue(asking.offered.isEmpty)
        XCTAssertFalse(core.sent.contains { $0.name == "export_drum_track" })
    }

    func testOpenWithHandsTheMusicXMLToTheChosenProgram() async throws {
        let (model, _) = try await model()
        let app = URL(fileURLWithPath: "/Applications/MuseScore 4.app")
        asking.program = app
        Exports.openWith(model)
        XCTAssertEqual(asking.opened.map(\.0.path), ["/c/e.musicxml"])
        XCTAssertEqual(asking.opened.map(\.1), [app])
        asking.program = nil
        Exports.openWith(model)
        XCTAssertEqual(asking.opened.count, 1)
    }

    /// The fixture's reply without its id, as ScriptedCore wants a reply's fields.
    func a4Pages() throws -> String {
        let url = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: "a4_pages", withExtension: "json"))
        let line = try String(contentsOf: url, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let prefix = #"{"id": 0, "#
        XCTAssertTrue(line.hasPrefix(prefix))
        return String(line.dropFirst(prefix.count).dropLast())
    }

    func testThePDFIsWrittenAndTheBarOffersToShowIt() async throws {
        let (model, _) = try await model(replies: ["a4_pages": try a4Pages()])
        let dest = temporary("eye.pdf")
        asking.save = dest
        await Exports.pdf(model)
        XCTAssertEqual(asking.offered, ["Eye of the Tiger.pdf"])
        XCTAssertEqual(asking.endings, [[]], "any name, as before")
        XCTAssertTrue(FileManager.default.fileExists(atPath: dest.path))
        XCTAssertEqual(model.notice?.opens, dest.path)
    }

    func testAPDFThatCannotBeWrittenSaysSo() async throws {
        let (model, _) = try await model(replies: ["a4_pages": try a4Pages()])
        asking.save = URL(fileURLWithPath: "/no-such-folder-\(UUID().uuidString)/eye.pdf")
        await Exports.pdf(model)
        XCTAssertNotNil(model.notice)
        XCTAssertNil(model.notice?.opens)
    }

    // MARK: Removal

    static let sizes = #""ok": true, "models": 2213000000, "everything": 2213400000, "#
        + #""models_text": "This frees 2.2 GB.", "everything_text": "This frees 2.3 GB.""#

    func testRemovalSendsTheReadersChoice() async throws {
        for (answer, sent) in [(false, Command.removeModels(everything: false)),
                               (true, Command.removeModels(everything: true))] {
            let (model, core) = try await model(replies: ["removal_sizes": Self.sizes])
            asking.remove = answer
            await Removal.ask(model)
            XCTAssertEqual(asking.sizes.last?.modelsText, "This frees 2.2 GB.")
            try await until { core.sent.contains(sent) }
        }
    }

    func testOnlyRemovingEverythingClearsWhatMacOSKeepsForTheApp() async throws {
        for (answer, cleared) in [(false, false), (true, true)] {
            Removal.everything = false
            let (model, core) = try await model(replies: ["removal_sizes": Self.sizes])
            asking.remove = answer
            await Removal.ask(model)
            try await until { core.sent.contains(.removeModels(everything: answer)) }
            XCTAssertEqual(Removal.everything, cleared)
        }
        Removal.everything = false
    }

    func testAKeptRemovalSendsNothing() async throws {
        let (model, core) = try await model(replies: ["removal_sizes": Self.sizes])
        asking.remove = nil
        await Removal.ask(model)
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertFalse(core.sent.contains { $0.name == "remove_models" })
    }

    // MARK: Panels

    func testAChosenSongIsOpened() async throws {
        let (model, core) = try await model()
        asking.chosenSong = URL(fileURLWithPath: "/m/b.flac")
        Panels.openSong(model)
        try await until { core.sent.contains(.open(path: "/m/b.flac")) }
        asking.chosenSong = nil
        Panels.openSong(model)
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertEqual(core.sent.filter { $0.name == "open" }.count, 1)
    }

    func testBeforeTheCoreRunsNothingIsOpenedExportedOrZoomed() async throws {
        let core = ScriptedCore(lines: [ScreenshotTests.result])
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "logic-\(UUID().uuidString)"))
        let model = AppModel(defaults: defaults, languages: ["en"]) { _ in core }
        XCTAssertEqual(model.phase, .launching)  // not launched: no core was made
        asking.chosenSong = URL(fileURLWithPath: "/m/b.flac")
        Panels.openSong(model)
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertTrue(core.sent.isEmpty)
        XCTAssertNil(Exports.result(model))
        XCTAssertFalse(ZoomMenu.enabled(model))
    }

    func testABuildWithoutItsCoreHasNoLicencesToShow() {
        // the tests' host is the app as built, before the core is put into it
        XCTAssertNil(SticklerCommands.licences)
    }

    func testOnlySoundFilesCountAsSongs() {
        XCTAssertTrue(Panels.isSong(URL(fileURLWithPath: "/m/a.flac")))
        XCTAssertTrue(Panels.isSong(URL(fileURLWithPath: "/m/a.mp3")))
        XCTAssertFalse(Panels.isSong(URL(fileURLWithPath: "/m/a.txt")))
    }

    // MARK: PageLoad

    func testAFinishedPageEndsTheWaitEvenIfItFinishedFirst() async throws {
        let load = PageLoad()
        load.webView(WKWebView(), didFinish: nil)
        load.webView(WKWebView(), didFail: nil, withError: SheetPDF.Failure.notDrawn)  // ignored
        try await load.finished()
    }

    func testAFailedPageFailsTheWait() async throws {
        for fail in [
            { (load: PageLoad) in
                load.webView(WKWebView(), didFail: nil, withError: SheetPDF.Failure.notDrawn)
            },
            { (load: PageLoad) in
                load.webView(
                    WKWebView(), didFailProvisionalNavigation: nil,
                    withError: SheetPDF.Failure.notDrawn)
            },
            { (load: PageLoad) in load.webViewWebContentProcessDidTerminate(WKWebView()) }
        ] {
            let load = PageLoad()
            Task { @MainActor in fail(load) }
            do {
                try await load.finished()
                XCTFail("a failed page must not finish")
            } catch {}
        }
    }
}


/// What "Remove Downloaded Models…" with everything removes besides Stickler's own folders.
@MainActor
final class LeftoversTests: XCTestCase {
    func testWhatMacOSKeepsForTheAppIsRemovedAndNothingElse() throws {
        let library = FileManager.default.temporaryDirectory
            .appendingPathComponent("stickler-leftovers-\(UUID().uuidString)")
        let places = Leftovers.places(identifier: "ng.tshia.Test", library: library)
        XCTAssertEqual(
            places.map { $0.path.dropFirst(library.path.count + 1) },
            [
                "Caches/ng.tshia.Test", "WebKit/ng.tshia.Test", "HTTPStorages/ng.tshia.Test",
                "Saved Application State/ng.tshia.Test.savedState",
                "Preferences/ng.tshia.Test.plist"
            ])
        let other = library.appendingPathComponent("Caches/com.example.Other/kept")
        for file in places.dropLast().map({ $0.appendingPathComponent("file") }) + [other] {
            try FileManager.default.createDirectory(
                at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
            try Data("x".utf8).write(to: file)
        }
        let suite = "stickler-leftovers-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defaults.set("here", forKey: "NSWindow Frame main")
        Leftovers.remove(identifier: suite, library: library, defaults: defaults)
        XCTAssertNil(defaults.string(forKey: "NSWindow Frame main"))
        Leftovers.remove(identifier: "ng.tshia.Test", library: library, defaults: defaults)
        for place in places {
            XCTAssertFalse(FileManager.default.fileExists(atPath: place.path), place.path)
        }
        XCTAssertTrue(FileManager.default.fileExists(atPath: other.path), "another app's stay")
        Leftovers.remove(identifier: nil, library: library, defaults: defaults)  // nothing to do
        try FileManager.default.removeItem(at: library)
        // the test's own preferences leave no file in the real Library either
        let real = try XCTUnwrap(
            FileManager.default.urls(for: .libraryDirectory, in: .userDomainMask).first)
        Leftovers.remove(identifier: suite, library: real, defaults: defaults)
    }
}

// MARK: Backups (an extension, so the class body stays within SwiftLint's length)

extension LogicTests {
    static let summary = #""ok": true, "created": "2026-11-22", "songs": 2, "size": 9, "#
        + #""text": "Made on 2026-11-22.""#

    func testABackupIsSavedUnderItsDatedName() async throws {
        let (model, core) = try await model()
        asking.save = URL(fileURLWithPath: "/Users/me/b.zip")
        let day = try XCTUnwrap(
            Calendar(identifier: .gregorian).date(from: DateComponents(
                year: 2026, month: 11, day: 22, hour: 12)))
        Backups.backUp(model, on: day)
        XCTAssertEqual(asking.offered.last, "Stickler Backup 2026-11-22.zip")
        XCTAssertEqual(asking.endings.last, ["zip"])
        try await until { core.sent.contains(.backUp(dest: "/Users/me/b.zip")) }
    }

    func testACancelledBackupSendsNothing() async throws {
        let (model, core) = try await model()
        asking.save = nil
        Backups.backUp(model)
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertFalse(core.sent.contains { $0.name == "back_up" })
    }

    func testARestoreAsksWithWhatTheBackupHolds() async throws {
        for answer in [true, false] {
            let (model, core) = try await model(replies: ["backup_summary": Self.summary])
            asking.chosenBackup = URL(fileURLWithPath: "/Users/me/b.zip")
            asking.restoreIt = answer
            await Backups.restore(model)
            XCTAssertEqual(asking.questions.last, "Made on 2026-11-22.")
            if answer {
                try await until { core.sent.contains(.restore(src: "/Users/me/b.zip")) }
            } else {
                try await Task.sleep(for: .milliseconds(100))
                XCTAssertFalse(core.sent.contains { $0.name == "restore" })
            }
        }
    }

    func testNoFileChosenAsksNothing() async throws {
        let (model, core) = try await model(replies: ["backup_summary": Self.summary])
        asking.chosenBackup = nil
        await Backups.restore(model)
        XCTAssertTrue(asking.questions.isEmpty)
        XCTAssertFalse(core.sent.contains { $0.name == "backup_summary" })
    }
}
