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
        XCTAssertFalse(view.configuration.websiteDataStore.isPersistent, "nothing left on disk")
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
}

/// How the sheet's pages get into the web view (SPEC.md, module `mac-sheet`, scope 2 and 3):
/// the document loaded once, later pages replacing the first in it, and a pinch's picture.
/// With a real web view in a window, as only WebKit can tell where a page is scrolled to.
@MainActor
final class SheetLoadTests: XCTestCase {
    /// Styles and sheets of a page `height` points high, with nothing around it.
    func tall(_ height: Int) -> SheetHTML.Content {
        SheetHTML.Content(
            style: "body { margin: 0; }", sheets: "<div style=\"height: \(height)px\"></div>")
    }

    /// A real web view in a window, and what loads its pages.
    struct Shown {
        let window: NSWindow
        let view: SheetWebView
        let load: SheetLoad
    }

    /// The sheet's web view in a window of 400 by 300 points.
    func sheetInAWindow() -> Shown {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 400, height: 300), styleMask: [.borderless],
            backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let view = SheetWebView.make()
        window.contentView = view
        let load = SheetLoad()
        view.navigationDelegate = load
        return Shown(window: window, view: view, load: load)
    }

    /// What the app's own script `script` gives in `view`'s page.
    func value(_ script: String, in view: WKWebView) async -> String {
        let value = try? await view.callAsyncJavaScript(script, contentWorld: .page)
        return value.map { "\($0)" } ?? "nothing"
    }

    /// Waits until `script` gives `wanted`, and gives what it gave last.
    func settles(_ script: String, at wanted: String, in view: WKWebView) async throws -> String {
        var tries = 0
        var now = await value(script, in: view)
        while now != wanted, tries < 250 {
            tries += 1
            try await Task.sleep(for: .milliseconds(20))
            now = await value(script, in: view)
        }
        return now
    }

    static let height = "return document.documentElement.scrollHeight"
    static let scrolled = "return window.scrollY"
    static let picture = "return document.body.style.transform"

    func testTheDocumentIsLoadedOnceAndAgainWhenWebKitsProcessDied() {
        let view = CountingWebView()
        let load = SheetLoad()
        XCTAssertTrue(load.show(tall(100), in: view))
        XCTAssertFalse(load.show(tall(100), in: view), "shown already")
        XCTAssertEqual(view.loaded, [tall(100).document])
        load.show(tall(200), in: view)  // the document still loads: these pages wait for it
        XCTAssertEqual(load.shown, tall(200))
        XCTAssertEqual(view.loaded, [tall(100).document])
        load.webViewWebContentProcessDidTerminate(view)
        XCTAssertEqual(view.loaded, [tall(100).document, tall(200).document])
        XCTAssertEqual(load.shown, tall(200))
    }

    func testPagesThatCameWhileTheDocumentLoadedReplaceItsOwn() async throws {
        let sheet = sheetInAWindow()
        let (view, load) = (sheet.view, sheet.load)
        load.show(tall(3000), in: view)
        load.show(tall(5000), in: view)
        load.show(tall(7000), in: view)
        let height = try await settles(Self.height, at: "7000", in: view)
        XCTAssertEqual(height, "7000")
        let sheets = await value("return document.body.children.length", in: view)
        XCTAssertEqual(sheets, "1", "the newest pages alone")
        sheet.window.close()
    }

    func testADocumentThatCannotTakeNewPagesIsLoadedAfresh() async throws {
        let view = CountingWebView()  // it loads nothing, so its page has no styles to replace
        let load = SheetLoad()
        load.show(tall(100), in: view)
        load.webView(view, didFinish: nil)
        load.show(tall(200), in: view)
        var tries = 0
        while view.loaded.count < 2, tries < 250 {
            tries += 1
            try await Task.sleep(for: .milliseconds(20))
        }
        XCTAssertEqual(view.loaded, [tall(100).document, tall(200).document])
    }

    /// Pages laid out again at twice the height show the same music, so the reader is twice
    /// as far down in points; the document is not loaded again for them.
    func testTheReaderStaysWhereTheyWereWhenThePagesAreLaidOutAgain() async throws {
        let sheet = sheetInAWindow()
        let (view, load) = (sheet.view, sheet.load)
        load.show(tall(3000), in: view)
        let first = try await settles(Self.height, at: "3000", in: view)
        XCTAssertEqual(first, "3000")
        let moved = await value(
            "window.kept = 7; window.scrollTo(0, 1500); return window.scrollY", in: view)
        XCTAssertEqual(moved, "1500")
        load.show(tall(6000), in: view)
        let kept = try await settles(Self.scrolled, at: "3000", in: view)
        XCTAssertEqual(kept, "3000")
        load.show(tall(12000), in: view)
        let grown = try await settles(Self.height, at: "12000", in: view)
        XCTAssertEqual(grown, "12000")
        let still = try await settles(Self.scrolled, at: "6000", in: view)
        XCTAssertEqual(still, "6000")
        let same = await value("return window.kept", in: view)
        XCTAssertEqual(same, "7", "the document was not loaded again")
        // a page from elsewhere is not shown
        view.loadHTMLString("<p>elsewhere</p>", baseURL: URL(string: "https://example.org/"))
        try await Task.sleep(for: .milliseconds(500))
        let height = await value(Self.height, in: view)
        XCTAssertEqual(height, "12000")
        sheet.window.close()
    }

    func testAfterWebKitsProcessDiedTheReaderIsBackWhereTheyWere() async throws {
        let sheet = sheetInAWindow()
        let (view, load) = (sheet.view, sheet.load)
        load.show(tall(3000), in: view)
        _ = try await settles(Self.height, at: "3000", in: view)
        _ = await value("window.scrollTo(0, 1500); return true", in: view)
        load.show(tall(6000), in: view)  // the place is read as these pages come
        _ = try await settles(Self.scrolled, at: "3000", in: view)
        _ = await value("window.kept = 7; return true", in: view)
        load.webViewWebContentProcessDidTerminate(view)
        let again = try await settles(
            "return window.kept === undefined ? window.scrollY : -1", at: "3000", in: view)
        XCTAssertEqual(again, "3000", "loaded again, and scrolled to the place")
        sheet.window.close()
    }

    // MARK: A pinch's picture

    func testAPinchsPictureFollowsTheFingersAndEndsWithItsPages() async throws {
        let sheet = sheetInAWindow()
        let (view, load) = (sheet.view, sheet.load)
        var scales: [Double] = []
        view.pinched = { scales.append($0) }
        load.show(tall(3000), in: view)
        _ = try await settles(Self.height, at: "3000", in: view)
        _ = await value("window.scrollTo(0, 200); return true", in: view)
        let fingers = CGPoint(x: 100, y: 50)
        view.pinch(.began, by: 0, at: fingers)
        view.pinch(.changed, by: 0.25, at: fingers)
        let larger = try await settles(Self.picture, at: "scale(1.25)", in: view)
        XCTAssertEqual(larger, "scale(1.25)")
        let around = await value("return document.body.style.transformOrigin", in: view)
        XCTAssertEqual(around, "100px 250px", "the point the pinch began at, in the page")
        view.pinch(.changed, by: 0.6, at: CGPoint(x: 300, y: 90))
        let twice = try await settles(Self.picture, at: "scale(2)", in: view)
        XCTAssertEqual(twice, "scale(2)")
        let fixed = await value("return document.body.style.transformOrigin", in: view)
        XCTAssertEqual(fixed, "100px 250px", "it does not wander with the fingers")
        XCTAssertEqual(scales, [], "the note size changes when the fingers lift")
        view.pinch(.ended, by: 0, at: fingers)
        XCTAssertEqual(scales, [2.0])
        try await Task.sleep(for: .milliseconds(200))
        let held = await value(Self.picture, in: view)
        XCTAssertEqual(held, "scale(2)", "the picture stays until its pages come")
        load.show(tall(6000), in: view)
        let gone = try await settles(Self.picture, at: "", in: view)
        XCTAssertEqual(gone, "")
        let place = await value(Self.scrolled, in: view)
        XCTAssertEqual(place, "400", "as far down the new pages as before the pinch")
        sheet.window.close()
    }

    func testAPinchsPictureIsTakenBackWhenNoPagesCome() async throws {
        let sheet = sheetInAWindow()
        let (view, load) = (sheet.view, sheet.load)
        view.patience = .milliseconds(100)
        load.show(tall(3000), in: view)
        _ = try await settles(Self.height, at: "3000", in: view)
        // cancelled by the system
        view.pinch(.began, by: 0)
        view.pinch(.changed, by: 0.5)
        _ = try await settles(Self.picture, at: "scale(1.5)", in: view)
        view.settle()  // the fingers are still down: the picture is theirs
        try await Task.sleep(for: .milliseconds(100))
        let theirs = await value(Self.picture, in: view)
        XCTAssertEqual(theirs, "scale(1.5)")
        view.pinch(.cancelled, by: 0)
        let cancelled = try await settles(Self.picture, at: "", in: view)
        XCTAssertEqual(cancelled, "")
        // back where it began: no new size
        view.pinch(.began, by: 0)
        view.pinch(.changed, by: 1)
        view.pinch(.changed, by: -0.5)
        view.pinch(.ended, by: 0)
        let unchanged = try await settles(Self.picture, at: "", in: view)
        XCTAssertEqual(unchanged, "")
        // the core refused the size, so no pages come: taken back after the wait
        view.pinch(.began, by: 0)
        view.pinch(.changed, by: 99)
        let largest = try await settles(Self.picture, at: "scale(5)", in: view)
        XCTAssertEqual(largest, "scale(5)", "the picture's own limit")
        view.pinch(.ended, by: 0)
        let refused = try await settles(Self.picture, at: "", in: view)
        XCTAssertEqual(refused, "")
        // the core answered with the pages shown already
        view.pinch(.began, by: 0)
        view.pinch(.changed, by: -0.9)
        _ = try await settles(Self.picture, at: "scale(0.2)", in: view)
        view.patience = .seconds(60)
        view.pinch(.ended, by: 0)
        view.settle()
        let same = try await settles(Self.picture, at: "", in: view)
        XCTAssertEqual(same, "")
        sheet.window.close()
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
