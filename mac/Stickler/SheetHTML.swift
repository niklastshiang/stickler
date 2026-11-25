import Foundation
import SticklerCore

/// The page the sheet's web view shows (SPEC.md, module `mac-sheet`, scope 2; design screen
/// M6): the core's pages one under the other on the grey desk, each on white paper with the
/// canvas's soft shadow. In dark mode the paper is inverted (light notes on a dark page), as
/// in the GTK app. Plain HTML and CSS without a script: the web view runs none.
enum SheetHTML {
    /// The desk around and between the pages, in points (the GTK sheet's gutter).
    static let gutter = 12.0

    /// The width to ask the core for: the web view's, less the desk on both sides. Nothing
    /// while the view is too narrow to show a page.
    static func pagesWidth(in view: Double) -> Double? {
        let width = view - 2 * gutter
        return width >= 1 ? width : nil
    }

    /// A colour as red, green and blue of 255.
    struct Colour: Equatable {
        let red: Int
        let green: Int
        let blue: Int
    }

    /// The desk's grey (M6): the page's background, and the web view's own where no page is.
    static func desk(dark: Bool) -> Colour {
        dark
            ? Colour(red: 0x14, green: 0x14, blue: 0x14)
            : Colour(red: 0xec, green: 0xec, blue: 0xee)
    }

    /// What VoiceOver reads for the sheet, which is one picture to it: the song's title and
    /// the page count ("Sheet music of Eye of the Tiger, 3 pages").
    static func label(title: String, pages: Int) -> String {
        localized("Sheet music of %1$@", title) + ", " + localized("%1$lld pages", pages)
    }

    /// Nothing is fetched for the page: the core's SVG brings its font and styles with it.
    static let policy =
        "default-src 'none'; style-src 'unsafe-inline'; font-src data:; img-src data:"

    /// What the web view shows: the page's styles and its sheets. The document is loaded once;
    /// pages laid out again replace both in it, so the sheet is never blank in between.
    struct Content: Equatable {
        let style: String
        let sheets: String

        /// The whole document, for the first load.
        var document: String {
            """
            <!doctype html><html><head><meta charset="utf-8">
            <meta http-equiv="Content-Security-Policy" content="\(SheetHTML.policy)"><style>
            \(style)
            </style></head><body aria-hidden="true">
            \(sheets)
            </body></html>
            """
        }
    }

    /// The styles and sheets for `pages` in the window's appearance; `below` points of desk
    /// stay free under the last page (the playback controls float there, M10).
    static func content(_ pages: [Page], dark: Bool, below: Double = 0) -> Content {
        // the canvas inverts a light grey paper, so the dark page is not pure black
        let paper =
            dark
            ? "background: #e4e4e6; filter: invert(1) hue-rotate(180deg);"
            : "background: #ffffff;"
        let desk = desk(dark: dark)
        // the paper inside the page, so the playback marker over it is not inverted with it
        let sheets = pages.map { page in
            "<div class=\"page\" style=\"width: \(page.width)px;\">"
                + "<div class=\"paper\">\(page.svg)</div></div>"
        }
        let style = """
            html { background: rgb(\(desk.red), \(desk.green), \(desk.blue)); overflow-x: hidden; }
            body { margin: 0; padding: \(gutter)px \(gutter)px \(gutter + below)px;
              cursor: default; -webkit-user-select: none; }
            .page { position: relative; margin: 0 auto \(gutter)px; }
            .paper { box-shadow: 0 1px 3px rgba(0,0,6,.18); \(paper) }
            .page:last-child { margin-bottom: 0; }
            .page svg { display: block; }
            #marker { position: absolute; border-radius: 5px; pointer-events: none; }
            """
        return Content(style: style, sheets: sheets.joined(separator: "\n"))
    }

    // the playback marker and a click on a bar (SPEC.md "Mac playback", scope 5): the app's
    // own scripts in the loaded page, whose own scripts stay off

    /// Draws the marker over a page's bar, or takes it away (`page` below 0), and scrolls it
    /// into view when it is not in the part of the window above the controls.
    static let markScript = """
        let mark = document.getElementById("marker");
        const host = page < 0 ? null : document.querySelectorAll(".page")[page];
        if (!host) { if (mark) { mark.remove(); } return false; }
        if (!mark) { mark = document.createElement("div"); mark.id = "marker"; }
        if (mark.parentNode !== host) { host.appendChild(mark); }
        mark.style.left = x + "px"; mark.style.top = y + "px";
        mark.style.width = width + "px"; mark.style.height = height + "px";
        mark.style.background = colour;
        const seen = mark.getBoundingClientRect();
        if (seen.top < 0 || seen.bottom > window.innerHeight - room) {
            window.scrollTo(0, window.scrollY + seen.top - (window.innerHeight - room) / 3);
        }
        return true
        """

    /// What the marker shows: sent again only when it changed or the pages were replaced.
    struct Marking: Equatable {
        let mark: Marker.Mark?
        let accent: Colour
        let dark: Bool
        let room: Double

        var arguments: [String: Any] {
            SheetHTML.markArguments(mark, accent: accent, dark: dark, room: room)
        }
    }

    /// The marker's script arguments: where `mark` is, in the accent colour (a fifth of it on
    /// white paper, a third on the dark page), keeping `room` points free above the window's
    /// bottom. No mark takes the marker away.
    static func markArguments(
        _ mark: Marker.Mark?, accent: Colour, dark: Bool, room: Double
    ) -> [String: Any] {
        guard let mark else {
            return ["page": -1, "x": 0, "y": 0, "width": 0, "height": 0, "colour": "", "room": 0]
        }
        let alpha = dark ? 0.32 : 0.2
        return [
            "page": mark.page, "x": mark.box.x, "y": mark.box.y, "width": mark.box.width,
            "height": mark.box.height,
            "colour": "rgba(\(accent.red), \(accent.green), \(accent.blue), \(alpha))",
            "room": room
        ]
    }

    /// The page under a point of the web view and the point on it, in page pixels: the
    /// script answers `[page, x, y]`, or nothing between the pages.
    static let hitScript = """
        const pages = document.querySelectorAll(".page");
        for (let k = 0; k < pages.length; k++) {
            const r = pages[k].getBoundingClientRect();
            if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) {
                return [k, x - r.left, y - r.top];
            }
        }
        return null
        """

    /// The written bar a click is on, from the hit script's answer and the shown pages.
    static func bar(hit answer: Any?, in pages: [Page]) -> Int? {
        guard let found = answer as? [Any], found.count == 3,
            let page = (found[0] as? NSNumber)?.intValue, pages.indices.contains(page),
            let x = (found[1] as? NSNumber)?.doubleValue,
            let y = (found[2] as? NSNumber)?.doubleValue
        else { return nil }
        return Marker.bar(atX: x, y: y, on: pages[page])
    }

    /// The whole document for `pages` in the window's appearance.
    static func document(_ pages: [Page], dark: Bool) -> String {
        content(pages, dark: dark).document
    }
}
