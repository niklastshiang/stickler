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

    /// The whole document for `pages` in the window's appearance.
    static func document(_ pages: [Page], dark: Bool) -> String {
        // the canvas inverts a light grey paper, so the dark page is not pure black
        let paper =
            dark
            ? "background: #e4e4e6; filter: invert(1) hue-rotate(180deg);"
            : "background: #ffffff;"
        let desk = desk(dark: dark)
        let sheets = pages.map { page in
            "<div class=\"page\" style=\"width: \(page.width)px;\">\(page.svg)</div>"
        }
        return """
            <!doctype html><html><head><meta charset="utf-8">
            <meta http-equiv="Content-Security-Policy" content="\(policy)"><style>
            html { background: rgb(\(desk.red), \(desk.green), \(desk.blue)); overflow-x: hidden; }
            body { margin: 0; padding: \(gutter)px; cursor: default; -webkit-user-select: none; }
            .page { margin: 0 auto \(gutter)px; box-shadow: 0 1px 3px rgba(0,0,6,.18); \(paper) }
            .page:last-child { margin-bottom: 0; }
            .page svg { display: block; }
            </style></head><body aria-hidden="true">
            \(sheets.joined(separator: "\n"))
            </body></html>
            """
    }
}
