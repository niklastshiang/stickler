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
        let model = AppModel(
            defaults: defaults, uvPlaces: [URL(fileURLWithPath: "/bin/sh")], languages: ["en"]
        ) { _, _, _ in core }
        let folder = FileManager.default.temporaryDirectory
            .appendingPathComponent("logic-\(UUID().uuidString)")
        try FileManager.default.createDirectory(
            at: folder.appendingPathComponent("adapters"), withIntermediateDirectories: true)
        try Data().write(to: folder.appendingPathComponent("pyproject.toml"))
        model.choose(folder: folder)
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

    func testAChosenFolderIsUsedAndACancelledOneChangesNothing() async throws {
        let (model, _) = try await model()
        let before = model.folder
        asking.chosenFolder = nil
        Panels.chooseFolder(model)
        XCTAssertEqual(model.folder, before)
        let other = temporary("not-stickler")
        try FileManager.default.createDirectory(at: other, withIntermediateDirectories: true)
        asking.chosenFolder = other
        Panels.chooseFolder(model)
        guard case .needsFolder(.notStickler) = model.phase else {
            return XCTFail("a folder without pyproject.toml is not Stickler: \(model.phase)")
        }
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

/// The reader's answers, fixed by each test; what was asked is kept.
@MainActor
final class FakeAsking: Asking {
    var save: URL?
    var chosenSong: URL?
    var chosenFolder: URL?
    var program: URL?
    var goOn = true
    var remove: Bool?
    private(set) var offered: [String] = []
    private(set) var costs: [String] = []
    private(set) var sizes: [RemovalSizes] = []
    private(set) var opened: [(URL, URL)] = []

    func saveLocation(named name: String) -> URL? {
        offered.append(name)
        return save
    }

    func song() -> URL? { chosenSong }

    func folder() -> URL? { chosenFolder }

    func application() -> URL? { program }

    func drumTrack(cost: String) -> Bool {
        costs.append(cost)
        return goOn
    }

    func removal(_ sizes: RemovalSizes) -> Bool? {
        self.sizes.append(sizes)
        return remove
    }

    func open(_ file: URL, with application: URL) {
        opened.append((file, application))
    }
}
