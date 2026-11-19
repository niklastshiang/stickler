import AppKit
import SticklerCore
import WebKit
import XCTest

@testable import Stickler

/// Design screen M6 in the screenshots (SPEC.md, module `mac-sheet`, Testing): the sheet
/// music from a fixed `pages` reply, and how the web view's page gets into a window's picture.
extension ScreenshotTests {
    static let settings = #""ok": true, "appearance": "system", "zoom": 1.0, "#
        + #""song_volume": 0.7, "hits_volume": 1.0, "setup_agreed": true, "percent": "100%""#

    /// The core's `pages` reply for the groove the Python tests engrave (tests/app/fakes.py),
    /// 876 pixels wide: its fields after the id, as `ScriptedCore` answers with them.
    static func pagesReply() throws -> String {
        let url = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: "pages", withExtension: "json"))
        let line = try String(contentsOf: url, encoding: .utf8)
        let start = #"{"id": 0, "#
        guard line.hasPrefix(start), line.hasSuffix("}") else {
            throw CocoaError(.fileReadCorruptFile)
        }
        return String(line.dropFirst(start.count).dropLast())
    }

    /// Waits up to `seconds` for `done`. It sleeps instead of turning the run loop, so the
    /// model's own tasks and WebKit's answers get the main actor meanwhile.
    func wait(_ seconds: Double, for done: @escaping () -> Bool) async throws {
        var waited = 0.0
        while !done(), waited < seconds {
            try await Task.sleep(for: .milliseconds(20))
            waited += 0.02
        }
    }

    /// The sheet's web view below `view`, when the window shows one.
    func sheetWeb(below view: NSView) -> SheetWebView? {
        if let found = view as? SheetWebView {
            return found
        }
        return view.subviews.lazy.compactMap { self.sheetWeb(below: $0) }.first
    }

    /// Draws the sheet's page into the window's picture. WebKit draws in a process of its own,
    /// so the window's own picture is blank where the web view is.
    func drawSheet(
        of model: AppModel, in frame: NSView, to bitmap: NSBitmapImageRep
    ) async throws {
        guard let web = sheetWeb(below: frame) else { return }
        try await wait(3) { !model.sheet.pages.isEmpty }
        // a first width that did not hold is asked for again after the model's pause
        try await Task.sleep(for: .milliseconds(500))
        try await wait(5) { !web.isLoading }
        try await Task.sleep(for: .milliseconds(300))
        let page = try await web.takeSnapshot(configuration: nil)
        var place = web.convert(web.bounds, to: frame)
        if frame.isFlipped {
            place.origin.y = frame.bounds.height - place.maxY
        }
        let context = try XCTUnwrap(NSGraphicsContext(bitmapImageRep: bitmap))
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = context
        page.draw(in: place)
        NSGraphicsContext.restoreGraphicsState()
    }
}
