import AppKit
import SticklerCore
import SwiftUI
import XCTest

@testable import Stickler

/// The website's pictures of the Mac app (SPEC.md "Website", "Change 2026-11-25"): the window
/// at 1000 × 700 points, as the GTK stills, with "Eyesplit" and Stickler's real transcription
/// of it (recorded by scripts/site_mac.py). The window server's own picture of the window is
/// taken, so the toolbar's glass and the floating controls come out as on screen; a window
/// drawn off screen leaves them blank. Saved as `site-<name>-light.png` and `-dark.png`;
/// `scripts/site_mac.py fetch` takes them into the site.
extension ScreenshotTests {
    static let siteSize = NSSize(width: 1000, height: 700)

    /// Only openly licensed songs: the example song and the two others heard on 2026-11-24.
    static let siteRecent = #"{"event": "recent", "seq": 2, "rows": ["#
        + #"{"path": "/Users/me/Music/Eyesplit.mp3", "title": "Eyesplit", "#
        + #""detail": "Shane Ivers · opened today", "missing": false}, "#
        + #"{"path": "/Users/me/Music/Hard Sell Hotel.mp3", "title": "Hard Sell Hotel", "#
        + #""detail": "Shane Ivers · opened yesterday", "missing": false}, "#
        + #"{"path": "/Users/me/Music/Chaos ID.mp3", "title": "Chaos ID", "#
        + #""detail": "Soularflair · 24 November", "missing": false}]}"#

    static let siteAnalysing = #"{"event": "state", "seq": 3, "state": {"kind": "analysing", "#
        + #""song": "/Users/me/Music/Eyesplit.mp3", "name": "Eyesplit", "#
        + #""steps": [{"id": "transcribe", "label": "Detect the hits", "#
        + #""detail": "Kick, snare, toms, hi-hat, cymbals", "state": "done"}, "#
        + #"{"id": "beats", "label": "Find the beat and the bars", "#
        + #""detail": "Tempo, time signature, the first “one”", "state": "running"}, "#
        + #"{"id": "engrave", "label": "Write the notes", "detail": "Bars, repeats, beams", "#
        + #""state": "waiting"}], "can_open": true, "can_cancel": true, "can_close": true}}"#

    /// A fixture's text without the line end the script writes.
    static func fixture(_ name: String) throws -> String {
        let url = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: name, withExtension: "json"), name)
        return try String(contentsOf: url, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// The core's `pages` reply for Eyesplit at 976 pixels: its fields after the id.
    static func sitePages() throws -> String {
        let line = try fixture("eyesplit_pages")
        let start = #"{"id": 0, "#
        guard line.hasPrefix(start), line.hasSuffix("}") else {
            throw CocoaError(.fileReadCorruptFile)
        }
        return String(line.dropFirst(start.count).dropLast())
    }

    /// The core's `result` state for Eyesplit, as it sends it after the analysis.
    static func siteResult() throws -> String {
        let state = try fixture("eyesplit_result")
        return #"{"event": "state", "seq": 3, "state": "# + state + "}"
    }

    func siteCore(_ lines: [String]) throws -> ScriptedCore {
        ScriptedCore(
            lines: lines,
            replies: [
                "pages": try Self.sitePages(), "settings": Self.settings,
                "volumes": #""ok": true, "song": 0.7, "hits": 1.0"#
            ])
    }

    func testTheWebsiteShowsTheEmptyWindow() async throws {
        let lines = [Self.empty, Self.siteRecent]
        let model = try await model(lines, core: try siteCore(lines))
        XCTAssertEqual(model.recent.count, 3)
        try await siteShoot(model, "empty")
    }

    func testTheWebsiteShowsTheAnalysis() async throws {
        let lines = [Self.empty, Self.siteRecent, Self.siteAnalysing]
        let model = try await model(lines, core: try siteCore(lines))
        XCTAssertEqual(model.title, "Eyesplit")
        try await siteShoot(model, "analysing")
    }

    func testTheWebsiteShowsTheSheetFollowingTheSong() async throws {
        let lines = [Self.empty, Self.siteRecent, try Self.siteResult()]
        let core = try siteCore(lines)
        let model = try await model(lines, core: core, player: QuietPlayer())
        try await wait(2) { model.playback.canPlay }
        model.playback.seek(to: 11.5)  // in bar 8, as the GTK still shows it
        XCTAssertEqual(model.title, "Eyesplit")
        XCTAssertEqual(model.subtitle, "Shane Ivers · ♩ = 154 · 4/4")
        XCTAssertEqual(model.playback.label, "Bar 8 of 97")
        XCTAssertEqual(model.playback.marked, 8)
        try await siteShoot(model, "sheet", sheet: true)
        // the window is 1000 points wide, the desk takes 12 on each side
        XCTAssertEqual(core.sent.last { $0.name == "pages" }, .pages(width: 976, zoom: nil))
    }

    /// The window with `model` at the site's size, in light and dark, as the window server
    /// draws it; with `sheet`, once the sheet's web view has its page.
    func siteShoot(_ model: AppModel, _ name: String, sheet: Bool = false) async throws {
        for (appearance, look) in [(NSAppearance.Name.aqua, "light"), (.darkAqua, "dark")] {
            let window = NSWindow(
                contentRect: NSRect(origin: .zero, size: Self.siteSize),
                styleMask: [.titled, .closable, .miniaturizable, .resizable],
                backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.appearance = NSAppearance(named: appearance)
            window.contentViewController = NSHostingController(rootView: ContentView(model: model))
            let place = NSRect(origin: NSPoint(x: 40, y: 40), size: Self.siteSize)
            window.setFrame(place, display: true)
            window.orderFrontRegardless()
            try await Task.sleep(for: .milliseconds(500))
            if sheet {
                let frame = try XCTUnwrap(window.contentView?.superview, "the frame view")
                let web = try XCTUnwrap(sheetWeb(below: frame), "the sheet's web view")
                try await wait(3) { !model.sheet.pages.isEmpty }
                // a first width that did not hold is asked for again after the model's pause
                try await Task.sleep(for: .milliseconds(500))
                try await wait(5) { !web.isLoading }
            }
            try await Task.sleep(for: .milliseconds(700))
            let file = Self.folder.appendingPathComponent("site-\(name)-\(look).png")
            try capture(window, to: file)
            let scale = window.backingScaleFactor
            window.orderOut(nil)
            let data = try Data(contentsOf: file)
            let bitmap = try XCTUnwrap(NSBitmapImageRep(data: data), "\(file.lastPathComponent)")
            XCTAssertEqual(bitmap.pixelsWide, Int(Self.siteSize.width * scale), "\(name) \(look)")
            XCTAssertEqual(bitmap.pixelsHigh, Int(Self.siteSize.height * scale), "\(name) \(look)")
            XCTAssertGreaterThan(colours(in: bitmap), 2, "\(name) \(look) is blank")
        }
    }

    /// The window server's picture of `window` alone, without its shadow.
    func capture(_ window: NSWindow, to file: URL) throws {
        try FileManager.default.createDirectory(at: Self.folder, withIntermediateDirectories: true)
        try? FileManager.default.removeItem(at: file)
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
        process.arguments = ["-x", "-o", "-l\(window.windowNumber)", file.path]
        try process.run()
        process.waitUntilExit()
        XCTAssertEqual(process.terminationStatus, 0, "screencapture \(file.lastPathComponent)")
    }
}
