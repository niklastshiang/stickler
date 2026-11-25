import AppKit
import SticklerCore
import WebKit
import XCTest

@testable import Stickler

/// The playback marker and a click on a bar (SPEC.md "Mac playback", scope 5).
extension SheetTests {
    static let accent = SheetHTML.Colour(red: 0, green: 96, blue: 223)
    static let box = BarBox(bar: 2, x: 10, y: 20, width: 30, height: 40)

    func testTheMarkerIsDrawnOverThePaperNotInvertedWithIt() throws {
        let dark = SheetHTML.document([try page("one")], dark: true)
        XCTAssertTrue(
            dark.contains(".paper { box-shadow: 0 1px 3px rgba(0,0,6,.18); background: #e4e4e6;"))
        XCTAssertTrue(dark.contains(".page { position: relative;"))
        XCTAssertTrue(dark.contains("#marker { position: absolute;"))
        XCTAssertTrue(dark.contains("<div class=\"paper\"><svg"))
        XCTAssertFalse(dark.contains("<script"))
    }

    func testTheMarkerIsTheBarsRectangleInTheAccentColour() {
        let mark = Marker.Mark(page: 1, box: Self.box)
        let light = SheetHTML.markArguments(mark, accent: Self.accent, dark: false, room: 84)
        XCTAssertEqual(light["page"] as? Int, 1)
        XCTAssertEqual(light["x"] as? Double, 10)
        XCTAssertEqual(light["y"] as? Double, 20)
        XCTAssertEqual(light["width"] as? Double, 30)
        XCTAssertEqual(light["height"] as? Double, 40)
        XCTAssertEqual(light["colour"] as? String, "rgba(0, 96, 223, 0.2)")
        XCTAssertEqual(light["room"] as? Double, 84)
        let dark = SheetHTML.Marking(mark: mark, accent: Self.accent, dark: true, room: 0)
        XCTAssertEqual(dark.arguments["colour"] as? String, "rgba(0, 96, 223, 0.32)")
        let none = SheetHTML.markArguments(nil, accent: Self.accent, dark: false, room: 84)
        XCTAssertEqual(none["page"] as? Int, -1, "no bar sounds: the marker goes")
    }

    func testAClickFindsTheBarUnderItFromThePagesAnswer() throws {
        let fields: [String: Any] = [
            "svg": "", "width": 800.0, "height": 100.0,
            "bars": [["bar": 2, "x": 10.0, "y": 20.0, "width": 30.0, "height": 40.0]]
        ]
        let data = try JSONSerialization.data(withJSONObject: fields)
        let pages = [try JSONDecoder().decode(Page.self, from: data)]
        let hit: [Any] = [NSNumber(value: 0), NSNumber(value: 25.0), NSNumber(value: 30.0)]
        XCTAssertEqual(SheetHTML.bar(hit: hit, in: pages), 2)
        let between: [Any] = [NSNumber(value: 0), NSNumber(value: 5.0), NSNumber(value: 5.0)]
        XCTAssertNil(SheetHTML.bar(hit: between, in: pages))
        XCTAssertNil(SheetHTML.bar(hit: nil, in: pages), "between the pages")
        XCTAssertNil(SheetHTML.bar(hit: [NSNumber(value: 1), NSNumber(value: 25.0)], in: pages))
        let gone: [Any] = [NSNumber(value: 3), NSNumber(value: 25.0), NSNumber(value: 30.0)]
        XCTAssertNil(SheetHTML.bar(hit: gone, in: pages), "a page no longer shown")
        XCTAssertNil(SheetHTML.bar(hit: ["0", "25", "30"], in: pages))
    }
}

extension SheetLoadTests {
    /// Two pages of 400 by 200 pixels as the app builds them.
    func twoPages() throws -> SheetHTML.Content {
        let page = try JSONDecoder().decode(
            Page.self,
            from: JSONSerialization.data(withJSONObject: [
                "svg": "<svg width=\"400px\" height=\"200px\"></svg>", "width": 400.0,
                "height": 200.0, "bars": [] as [Any]
            ]))
        return SheetHTML.content([page, page], dark: false)
    }

    static let marker = """
        const m = document.getElementById("marker");
        if (!m) { return "none"; }
        const pages = Array.from(document.querySelectorAll(".page"));
        return pages.indexOf(m.parentNode) + " " + m.style.left + " " + m.style.top
        """

    func testTheMarkerIsDrawnMovedKeptWithNewPagesAndTakenAway() async throws {
        let sheet = sheetInAWindow()
        let (view, load) = (sheet.view, sheet.load)
        let content = try twoPages()
        let accent = SheetHTML.Colour(red: 0, green: 96, blue: 223)
        let first = SheetHTML.Marking(
            mark: Marker.Mark(page: 0, box: BarBox(bar: 1, x: 10, y: 20, width: 30, height: 40)),
            accent: accent, dark: false, room: 0)
        load.show(content, in: view)
        load.mark(first, in: view, again: false)  // drawn once the document is there
        let drawn = try await settles(Self.marker, at: "0 10px 20px", in: view)
        XCTAssertEqual(drawn, "0 10px 20px")

        let second = SheetHTML.Marking(
            mark: Marker.Mark(page: 1, box: BarBox(bar: 5, x: 50, y: 60, width: 30, height: 40)),
            accent: accent, dark: false, room: 0)
        load.mark(second, in: view, again: false)
        let moved = try await settles(Self.marker, at: "1 50px 60px", in: view)
        XCTAssertEqual(moved, "1 50px 60px")
        XCTAssertEqual(load.marking, second)

        // new pages take the marker with them; it is drawn again over them
        let replaced = SheetHTML.content([], dark: true)
        XCTAssertTrue(load.show(replaced, in: view))
        load.mark(second, in: view, again: true)
        load.show(content, in: view)
        load.mark(second, in: view, again: true)
        let again = try await settles(Self.marker, at: "1 50px 60px", in: view)
        XCTAssertEqual(again, "1 50px 60px")

        let gone = SheetHTML.Marking(mark: nil, accent: accent, dark: false, room: 0)
        load.mark(gone, in: view, again: false)
        let none = try await settles(Self.marker, at: "none", in: view)
        XCTAssertEqual(none, "none")
        sheet.window.close()
    }

    func testAMarkerBelowTheWindowIsScrolledIntoView() async throws {
        let sheet = sheetInAWindow()  // 300 points high
        let (view, load) = (sheet.view, sheet.load)
        load.show(try twoPages(), in: view)
        _ = try await settles("return document.querySelectorAll('.page').length", at: "2", in: view)
        let low = SheetHTML.Marking(
            mark: Marker.Mark(page: 1, box: BarBox(bar: 5, x: 10, y: 150, width: 30, height: 40)),
            accent: SheetHTML.Colour(red: 0, green: 96, blue: 223), dark: false, room: 84)
        load.mark(low, in: view, again: false)
        let scrolled = try await settles(
            "return window.scrollY > 0 ? \"moved\" : \"still\"", at: "moved", in: view)
        XCTAssertEqual(scrolled, "moved")
        sheet.window.close()
    }

    func testAClickSaysWhichPageAndPointItLandedOn() async throws {
        let sheet = sheetInAWindow()
        let (view, load) = (sheet.view, sheet.load)
        load.show(try twoPages(), in: view)
        _ = try await settles("return document.querySelectorAll('.page').length", at: "2", in: view)
        var answers: [Any?] = []
        view.clicked = { answers.append($0) }
        view.click(at: CGPoint(x: 200, y: 112))  // the first page: 12 points of desk above it
        view.click(at: CGPoint(x: 200, y: 5))  // the desk above the pages
        for _ in 0..<250 where answers.count < 2 {
            try await Task.sleep(for: .milliseconds(20))
        }
        XCTAssertEqual(answers.count, 2)
        let first = try XCTUnwrap(answers.first as? [Any])
        XCTAssertEqual((first[0] as? NSNumber)?.intValue, 0)
        XCTAssertEqual((first[2] as? NSNumber)?.doubleValue ?? -1, 100, accuracy: 0.5)
        XCTAssertFalse(answers.last.flatMap { $0 } is [Any], "no page under the desk")
        sheet.window.close()
    }
}
