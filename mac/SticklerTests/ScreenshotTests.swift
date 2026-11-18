import AppKit
import SticklerCore
import SwiftUI
import XCTest

@testable import Stickler

/// Each screen drawn from the lines the real core sends (`ScriptedCore`), in light and dark,
/// saved as PNG for the owner to compare with the canvas (SPEC.md, module `mac-shell`,
/// Testing). CI keeps them as an artifact; `STICKLER_SCREENSHOTS` names the folder.
@MainActor
final class ScreenshotTests: XCTestCase {
    static let folder: URL = {
        let named = ProcessInfo.processInfo.environment["STICKLER_SCREENSHOTS"]
        return named.map { URL(fileURLWithPath: $0) }
            ?? FileManager.default.temporaryDirectory.appendingPathComponent("stickler-screens")
    }()

    static let recent = #"{"event": "recent", "seq": 2, "rows": ["#
        + #"{"path": "/Users/me/Music/Eye of the Tiger.flac", "title": "Eye of the Tiger", "#
        + #""detail": "Survivor · opened today", "missing": false}, "#
        + #"{"path": "/Users/me/Music/Fluffing a Duck.mp3", "title": "Fluffing a Duck", "#
        + #""detail": "Kevin MacLeod · opened yesterday", "missing": false}, "#
        + #"{"path": "/Users/me/Music/Gone.flac", "title": "Highway to Hell", "#
        + #""detail": "AC/DC · 15 November", "missing": true}]}"#

    static let empty = #"{"event": "state", "seq": 1, "#
        + #""state": {"kind": "empty", "can_open": true}}"#

    static let result = #"{"event": "state", "seq": 3, "state": {"kind": "result", "#
        + #""song": "/Users/me/Music/Eye of the Tiger.flac", "title": "Eye of the Tiger", "#
        + #""subtitle": "Survivor · ♩ = 109 · 4/4", "artist": "Survivor", "seconds": 246.0, "#
        + #""tempo": 109, "meter": [4, 4], "musicxml": "/c/e.musicxml", "corrections": "#
        + #"{"tempo": "normal", "beats_per_bar": null, "first_downbeat": null, "simplify": true, "#
        + #""repeats": true}, "correcting": false, "can_open": true, "can_close": true, "#
        + #""can_export": true}}"#

    /// A model whose core plays `lines`, its folder a Stickler checkout of its own.
    func model(_ lines: [String]?, core given: (any Core)? = nil) async throws -> AppModel {
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "screens-\(UUID().uuidString)"))
        let core = given ?? ScriptedCore(lines: lines ?? [])
        let model = AppModel(
            defaults: defaults, uvPlaces: [URL(fileURLWithPath: "/bin/sh")], languages: ["en"]
        ) { _, _, _ in core }
        guard let lines else { return model }  // the first start: no folder yet
        let folder = FileManager.default.temporaryDirectory
            .appendingPathComponent("screens-\(UUID().uuidString)")
        try FileManager.default.createDirectory(
            at: folder.appendingPathComponent("adapters"), withIntermediateDirectories: true)
        try Data().write(to: folder.appendingPathComponent("pyproject.toml"))
        model.choose(folder: folder)
        for _ in 0..<200 where model.recent.isEmpty && !lines.isEmpty {
            try await Task.sleep(for: .milliseconds(10))
        }
        try await Task.sleep(for: .milliseconds(50))
        return model
    }

    /// The window with `model`, drawn and saved as `<name>-light.png` and `<name>-dark.png`.
    func shoot(_ model: AppModel, _ name: String) throws {
        for (appearance, look) in [(NSAppearance.Name.aqua, "light"), (.darkAqua, "dark")] {
            let window = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 900, height: 620),
                styleMask: [.titled, .closable, .miniaturizable, .resizable],
                backing: .buffered, defer: false)
            window.appearance = NSAppearance(named: appearance)
            window.contentViewController = NSHostingController(rootView: ContentView(model: model))
            window.setContentSize(NSSize(width: 900, height: 620))
            window.orderFront(nil)
            RunLoop.main.run(until: Date().addingTimeInterval(0.5))
            let frame = try XCTUnwrap(window.contentView?.superview, "the window's frame view")
            let bitmap = try XCTUnwrap(frame.bitmapImageRepForCachingDisplay(in: frame.bounds))
            frame.cacheDisplay(in: frame.bounds, to: bitmap)
            window.orderOut(nil)
            XCTAssertGreaterThan(colours(in: bitmap), 2, "\(name) \(look) is blank")
            let png = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
            try FileManager.default.createDirectory(
                at: Self.folder, withIntermediateDirectories: true)
            try png.write(to: Self.folder.appendingPathComponent("\(name)-\(look).png"))
        }
    }

    /// How many different colours a sample of the image has (a blank one has one).
    func colours(in bitmap: NSBitmapImageRep) -> Int {
        var seen = Set<String>()
        for x in stride(from: 0, to: bitmap.pixelsWide, by: 23) {
            for y in stride(from: 0, to: bitmap.pixelsHigh, by: 23) {
                if let colour = bitmap.colorAt(x: x, y: y) {
                    seen.insert(colour.description)
                }
            }
        }
        return seen.count
    }

    func testTheFirstStartAsksForTheFolder() async throws {
        let model = try await model(nil)
        XCTAssertEqual(model.phase, .needsFolder(nil))
        try shoot(model, "M0-folder")
    }

    func testTheEmptyWindowShowsTheRecentSongs() async throws {
        let model = try await model([Self.empty, Self.recent])
        XCTAssertEqual(model.recent.count, 3)
        XCTAssertEqual(model.title, "Stickler")
        try shoot(model, "M4-empty")
    }

    func testAResultWaitsForTheSheetViewAndIsExported() async throws {
        let model = try await model([Self.empty, Self.recent, Self.result])
        XCTAssertEqual(model.title, "Eye of the Tiger")
        XCTAssertEqual(model.subtitle, "Survivor · ♩ = 109 · 4/4")
        try shoot(model, "M6-placeholder")
    }

    static let analysing = #"{"event": "state", "seq": 4, "state": {"kind": "analysing", "#
        + #""song": "/Users/me/Music/Eye of the Tiger.flac", "name": "Eye of the Tiger", "#
        + #""steps": [{"id": "transcribe", "label": "Detect the hits", "#
        + #""detail": "Kick, snare, toms, hi-hat, cymbals", "state": "done"}, "#
        + #"{"id": "beats", "label": "Find the beat and the bars", "#
        + #""detail": "Tempo, time signature, the first “one”", "state": "running"}, "#
        + #"{"id": "engrave", "label": "Write the notes", "detail": "Bars, repeats, beams", "#
        + #""state": "waiting"}], "can_open": true, "can_cancel": true, "can_close": true}}"#

    static let failed = #"{"event": "state", "seq": 4, "state": {"kind": "failed", "#
        + #""song": "/Users/me/Music/Eye of the Tiger.flac", "name": "Eye of the Tiger", "#
        + #""reason": "analysis", "title": "The Analysis Failed", "#
        + #""description": "Something went wrong while listening to “Eye of the Tiger.flac”.", "#
        + #""details": "adtof (exit 1): out of memory", "can_open": true, "can_retry": true, "#
        + #""can_close": true}}"#

    func testTheAnalysisShowsItsSteps() async throws {
        let model = try await model([Self.empty, Self.recent, Self.analysing])
        XCTAssertEqual(model.title, "Eye of the Tiger")
        XCTAssertTrue(model.state.can.cancel)
        try shoot(model, "M5-analysing")
    }

    func testAFailedSongSaysWhatHappenedAndCanBeTriedAgain() async throws {
        let model = try await model([Self.empty, Self.recent, Self.failed])
        XCTAssertTrue(model.state.can.retry)
        try shoot(model, "M5-failed")
    }

    func testAStoppedCoreSaysSoAndCanBeStartedAgain() async throws {
        let core = DyingCore()
        let model = try await model([], core: core)
        core.die(CoreEnd(reason: .signalled(9), details: ["Traceback (most recent call last):"]))
        for _ in 0..<200 where model.phase == .running {
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTAssertEqual(
            model.phase, .stopped(CoreEnd(reason: .signalled(9), details: [
                "Traceback (most recent call last):"
            ])))
        try shoot(model, "stopped")
    }

    func testOnlySoundFilesAreTakenWhenDropped() {
        XCTAssertTrue(Panels.isSong(URL(fileURLWithPath: "/m/Eye of the Tiger.flac")))
        XCTAssertTrue(Panels.isSong(URL(fileURLWithPath: "/m/a.MP3")))
        XCTAssertFalse(Panels.isSong(URL(fileURLWithPath: "/m/notes.txt")))
        XCTAssertFalse(Panels.isSong(URL(fileURLWithPath: "/m/folder")))
    }
}

/// A core that ends when the test says so.
final class DyingCore: Core, @unchecked Sendable {
    private let lock = NSLock()
    private var end: (@Sendable (CoreEnd) -> Void)?

    func start(
        onEvent _: @escaping @Sendable (Incoming) -> Void,
        onEnd: @escaping @Sendable (CoreEnd) -> Void
    ) {
        lock.withLock { end = onEnd }
    }

    func send(_: Command) async throws -> Reply {
        throw CoreClientError.notRunning
    }

    func quit(seconds _: Double) async {}

    func die(_ how: CoreEnd) {
        lock.withLock { end }?(how)
    }
}
