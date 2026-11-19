import AppKit
import SticklerCore
import WebKit
import XCTest

@testable import Stickler

/// The sheet in the window (SPEC.md, module `mac-sheet`, Testing): the page `SheetHTML` builds
/// for the web view, and what the web view itself must do without being asked by a page.
@MainActor
final class SheetTests: XCTestCase {
    /// A page as the core sends one; `mark` stands in for its notes.
    func page(_ mark: String, width: Double = 800) throws -> Page {
        let svg = "<svg width=\"\(width)px\" height=\"100px\"><desc>\(mark)</desc></svg>"
        let fields: [String: Any] = ["svg": svg, "width": width, "height": 100.0, "bars": []]
        return try JSONDecoder().decode(
            Page.self, from: JSONSerialization.data(withJSONObject: fields))
    }

    // MARK: The page

    func testThePageRunsNoScriptAndIsInvertedOnlyInDarkMode() throws {
        let pages = [try page("one")]
        let light = SheetHTML.document(pages, dark: false)
        XCTAssertFalse(light.contains("<script"))
        XCTAssertFalse(light.contains("invert("))
        XCTAssertTrue(light.contains("background: #ffffff;"))
        XCTAssertTrue(light.contains("html { background: rgb(236, 236, 238);"))
        let dark = SheetHTML.document(pages, dark: true)
        XCTAssertFalse(dark.contains("<script"))
        XCTAssertTrue(dark.contains("filter: invert(1) hue-rotate(180deg);"))
        XCTAssertTrue(dark.contains("html { background: rgb(20, 20, 20);"))
        for document in [light, dark] {
            XCTAssertTrue(document.contains("box-shadow: 0 1px 3px"), "the canvas's soft shadow")
            XCTAssertTrue(document.contains("overflow-x: hidden"), "it scrolls vertically only")
        }
    }

    func testThePageFetchesNothing() throws {
        let document = SheetHTML.document([try page("one")], dark: false)
        XCTAssertTrue(
            document.contains(
                "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "))
        XCTAssertTrue(SheetHTML.policy.contains("font-src data:"), "Verovio's embedded font")
    }

    func testThePagesComeInOrderEachAsWideAsItWasEngraved() throws {
        let pages = [try page("first"), try page("second", width: 640), try page("third")]
        let document = SheetHTML.document(pages, dark: false)
        let places = try ["first", "second", "third"].map { mark in
            try XCTUnwrap(document.range(of: "<desc>\(mark)</desc>")).lowerBound
        }
        XCTAssertEqual(places, places.sorted())
        XCTAssertEqual(document.components(separatedBy: "<div class=\"page\"").count - 1, 3)
        XCTAssertTrue(document.contains("<div class=\"page\" style=\"width: 640.0px;\"><svg"))
    }

    func testWithoutPagesOnlyTheDeskIsShown() {
        let document = SheetHTML.document([], dark: true)
        XCTAssertFalse(document.contains("<div class=\"page\""))
        XCTAssertTrue(document.contains("html { background: rgb(20, 20, 20);"))
    }

    func testTheWidthAskedForLeavesTheDeskOnBothSides() {
        XCTAssertEqual(SheetHTML.pagesWidth(in: 900), 876)
        XCTAssertEqual(SheetHTML.pagesWidth(in: 25), 1)
        XCTAssertNil(SheetHTML.pagesWidth(in: 24))
        XCTAssertNil(SheetHTML.pagesWidth(in: 0))
    }

    func testVoiceOverReadsTheTitleAndThePageCount() {
        XCTAssertEqual(
            SheetHTML.label(title: "Eye of the Tiger", pages: 3),
            "Sheet music of Eye of the Tiger, 3 pages")
        XCTAssertEqual(SheetHTML.label(title: "Groove", pages: 1), "Sheet music of Groove, 1 page")
    }

    // MARK: The web view

    func testTheWebViewRunsNoScriptAndLeavesTheKeyboardToTheWindow() {
        let view = SheetWebView.make()
        XCTAssertFalse(view.configuration.defaultWebpagePreferences.allowsContentJavaScript)
        XCTAssertFalse(view.acceptsFirstResponder)
        XCTAssertFalse(view.allowsMagnification)
        XCTAssertFalse(view.allowsBackForwardNavigationGestures)
    }

    func testTheWebViewTellsEachNewWidthOnce() {
        let view = SheetWebView.make()
        var widths: [Double] = []
        view.resized = { widths.append($0) }
        view.setFrameSize(NSSize(width: 900, height: 600))
        view.setFrameSize(NSSize(width: 900, height: 480))  // only the height changed
        view.setFrameSize(NSSize(width: 700, height: 480))
        view.setFrameSize(.zero)  // not shown: nothing to engrave for
        XCTAssertEqual(widths, [900, 700])
    }

    func testADroppedSongIsLeftToTheWindow() {
        XCTAssertEqual(SheetWebView.make().registeredDraggedTypes, [])
    }

    func testOnlyTheAppsOwnPageIsShown() {
        XCTAssertTrue(SheetLoad.allows(.other, to: URL(string: "about:blank")))
        XCTAssertFalse(SheetLoad.allows(.linkActivated, to: URL(string: "about:blank")))
        XCTAssertFalse(SheetLoad.allows(.other, to: URL(string: "https://example.org/")))
        XCTAssertFalse(SheetLoad.allows(.other, to: URL(fileURLWithPath: "/m/song.flac")))
        XCTAssertFalse(SheetLoad.allows(.other, to: nil))
    }

    func testAPinchTellsItsScaleOnceWhenTheFingersLift() {
        let view = SheetWebView.make()
        var scales: [Double] = []
        view.pinched = { scales.append($0) }
        view.pinch(.began, by: 0)
        view.pinch(.changed, by: 0.25)
        view.pinch(.changed, by: 0.6)
        XCTAssertEqual(scales, [], "nothing while the fingers move")
        view.pinch(.ended, by: 0)
        XCTAssertEqual(scales, [2.0])  // 1.25 × 1.6
    }

    func testACancelledPinchAndOneThatChangedNothingTellNothing() {
        let view = SheetWebView.make()
        var scales: [Double] = []
        view.pinched = { scales.append($0) }
        view.pinch(.began, by: 0)
        view.pinch(.changed, by: 0.5)
        view.pinch(.cancelled, by: 0)
        view.pinch(.ended, by: 0)
        view.pinch(.began, by: 0)
        view.pinch(.ended, by: 0)
        XCTAssertEqual(scales, [])
    }

    func testTheWebViewOffersNoMenu() {
        let menu = NSMenu()
        menu.addItem(withTitle: "Reload", action: nil, keyEquivalent: "")
        SheetWebView.make().willOpenMenu(menu, with: NSEvent())
        XCTAssertEqual(menu.items.count, 0)
    }

    func testAPageIsLoadedOnceAndAgainWhenWebKitsProcessDied() async throws {
        let view = CountingWebView()
        let load = SheetLoad()
        load.show("a", in: view)
        load.show("a", in: view)
        XCTAssertEqual(view.loaded, ["a"])
        load.show("b", in: view)  // loaded once the place in "a" is read
        XCTAssertEqual(load.shown, "b")
        var tries = 0
        while view.loaded.count < 2, tries < 250 {
            tries += 1
            try await Task.sleep(for: .milliseconds(20))
        }
        XCTAssertEqual(view.loaded, ["a", "b"])
        load.webViewWebContentProcessDidTerminate(view)
        XCTAssertEqual(view.loaded, ["a", "b", "b"])
        XCTAssertEqual(load.shown, "b")
    }

    func testOfTwoPagesAskedForAtOnceOnlyTheNewerIsLoaded() async throws {
        let view = CountingWebView()
        let load = SheetLoad()
        load.show("a", in: view)
        load.show("b", in: view)
        load.show("c", in: view)
        var tries = 0
        while view.loaded.count < 2, tries < 250 {
            tries += 1
            try await Task.sleep(for: .milliseconds(20))
        }
        try await Task.sleep(for: .milliseconds(200))
        XCTAssertEqual(view.loaded, ["a", "c"])
    }

    /// A real web view in a window: pages laid out again at twice the height show the same
    /// music, so the reader is twice as far down in points.
    func testTheReaderStaysWhereTheyWereWhenThePagesAreLaidOutAgain() async throws {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 400, height: 300), styleMask: [.borderless],
            backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let view = SheetWebView.make()
        window.contentView = view
        let load = SheetLoad()
        view.navigationDelegate = load
        func tall(_ height: Int) -> String {
            "<!doctype html><html><body style=\"margin: 0\">"
                + "<div style=\"height: \(height)px\"></div></body></html>"
        }
        func number(_ script: String) async -> Double {
            let value = try? await view.callAsyncJavaScript(script, contentWorld: .page)
            return value as? Double ?? -1
        }
        func settles(_ script: String, at wanted: Double) async throws -> Double {
            var tries = 0
            var value = await number(script)
            while value != wanted, tries < 250 {
                tries += 1
                try await Task.sleep(for: .milliseconds(20))
                value = await number(script)
            }
            return value
        }
        let height = "return document.documentElement.scrollHeight"
        load.show(tall(3000), in: view)
        let first = try await settles(height, at: 3000)
        XCTAssertEqual(first, 3000)
        let moved = await number("window.scrollTo(0, 1500); return window.scrollY")
        XCTAssertEqual(moved, 1500)
        load.show(tall(6000), in: view)
        let kept = try await settles("return window.scrollY", at: 3000)
        XCTAssertEqual(kept, 3000)
        load.show(tall(12000), in: view)
        let grown = try await settles(height, at: 12000)
        XCTAssertEqual(grown, 12000)
        let still = try await settles("return window.scrollY", at: 6000)
        XCTAssertEqual(still, 6000)
        // a page from elsewhere is not shown
        view.loadHTMLString(tall(50), baseURL: URL(string: "https://example.org/"))
        try await Task.sleep(for: .milliseconds(500))
        let same = await number(height)
        XCTAssertEqual(same, 12000)
        window.close()
    }

    func testNothingIsLoadedAgainBeforeAPageWasShown() {
        let view = CountingWebView()
        SheetLoad().webViewWebContentProcessDidTerminate(view)
        XCTAssertEqual(view.loaded, [])
    }
}

/// A web view that only notes what it was asked to load.
final class CountingWebView: WKWebView {
    var loaded: [String] = []

    override func loadHTMLString(_ string: String, baseURL _: URL?) -> WKNavigation? {
        loaded.append(string)
        return nil
    }
}
