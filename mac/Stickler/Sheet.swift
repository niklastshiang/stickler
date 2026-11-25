import AppKit
import SticklerCore
import SwiftUI
import WebKit

/// Design screen M6: the result's sheet music, as wide as the window. The model says which
/// pages (`SheetModel`); this only draws them and tells the model the width they have.
struct SheetView: View {
    let model: AppModel
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let dark = scheme == .dark
        SheetWeb(
            content: SheetHTML.content(
                model.sheet.pages, dark: dark,
                below: model.playback.canPlay ? Playbar.room : 0),
            dark: dark,
            mark: model.playback.marked.flatMap { Marker.locate($0, in: model.sheet.pages) },
            room: model.playback.canPlay ? Playbar.room : 0,
            resized: { width in
                if let pages = SheetHTML.pagesWidth(in: width) {
                    model.sheet.resize(to: pages)
                }
            },
            pinched: { scale in model.sheet.pinched(by: scale) },
            clicked: { answer in
                // a click on a bar plays from it (M10); the sheet's pages say which bar
                if let bar = SheetHTML.bar(hit: answer, in: model.sheet.pages) {
                    model.playback.jump(toBar: bar)
                }
            })
        // one picture to VoiceOver, not the notes' hundreds of shapes
        .accessibilityElement(children: .ignore)
        .accessibilityAddTraits(.isImage)
        .accessibilityLabel(
            Text(verbatim: SheetHTML.label(title: model.title, pages: model.sheet.pages.count)))
    }
}

/// The web view in SwiftUI: it shows `content`, loaded once; later pages replace the first.
/// The playback marker is drawn over `mark` in the system's accent colour.
struct SheetWeb: NSViewRepresentable {
    let content: SheetHTML.Content
    let dark: Bool
    let mark: Marker.Mark?
    let room: Double
    let resized: @MainActor (Double) -> Void
    let pinched: @MainActor (Double) -> Void
    let clicked: @MainActor (Any?) -> Void

    func makeCoordinator() -> SheetLoad {
        SheetLoad()
    }

    func makeNSView(context: Context) -> SheetWebView {
        let view = SheetWebView.make()
        view.navigationDelegate = context.coordinator
        return view
    }

    func updateNSView(_ view: SheetWebView, context: Context) {
        view.resized = resized
        view.pinched = pinched
        view.clicked = clicked
        let desk = SheetHTML.desk(dark: dark)
        view.underPageBackgroundColor = NSColor(
            srgbRed: CGFloat(desk.red) / 255, green: CGFloat(desk.green) / 255,
            blue: CGFloat(desk.blue) / 255, alpha: 1)
        let replaced = context.coordinator.show(content, in: view)
        if !replaced {
            view.settle()  // no new pages: a lifted pinch's picture has nothing to wait for
        }
        let accent = NSColor.controlAccentColor.usingColorSpace(.sRGB) ?? .systemBlue
        let marking = SheetHTML.Marking(
            mark: mark,
            accent: SheetHTML.Colour(
                red: Int(accent.redComponent * 255), green: Int(accent.greenComponent * 255),
                blue: Int(accent.blueComponent * 255)),
            dark: dark, room: room)
        context.coordinator.mark(marking, in: view, again: replaced)
    }
}

/// What the web view shows now. The document is loaded once; pages laid out again (a resize,
/// another note size, the other appearance) replace the old ones in it, at the place the
/// reader was: as far down the new pages as they had scrolled down the old ones. So the sheet
/// is never blank in between, and a pinch's picture ends in the same frame as its pages come.
/// When WebKit's drawing process dies, the document is loaded again instead of leaving the
/// sheet blank.
@MainActor
final class SheetLoad: NSObject, WKNavigationDelegate {
    private(set) var shown: SheetHTML.Content?
    /// What the document being loaded, or the loaded one, was built from.
    private var document: SheetHTML.Content?
    private var loaded = false  // the document is there and takes new pages
    /// How far down the reader was: 0 the top, 1 the page's whole height.
    private var place = 0.0
    /// The playback marker, drawn again after the pages are replaced or loaded.
    private(set) var marking: SheetHTML.Marking?

    /// The app's own scripts, which run although the page's are off.
    static let goToPlace =
        "window.scrollTo(0, place * document.documentElement.scrollHeight); return true"
    /// New styles and sheets in the loaded document; a pinch's picture ends with them. It
    /// gives the place the reader was at.
    static let replace = """
        const root = document.documentElement;
        document.body.style.transform = "";
        const place = window.scrollY / Math.max(1, root.scrollHeight);
        document.querySelector("style").textContent = style;
        document.body.innerHTML = sheets;
        window.scrollTo(0, place * root.scrollHeight);
        return place
        """

    /// Shows `content`; false when it is shown already.
    @discardableResult
    func show(_ content: SheetHTML.Content, in view: WKWebView) -> Bool {
        guard content != shown else { return false }
        let first = shown == nil
        shown = content
        if first {
            load(content, in: view)
        } else if loaded {
            replace(with: content, in: view)
        }
        // a document still loading takes the newest pages once it is there
        return true
    }

    /// Draws `next` unless it is drawn already; `again` after the pages were replaced, which
    /// took the marker with them. A document still loading gets it once it is there.
    func mark(_ next: SheetHTML.Marking, in view: WKWebView, again: Bool) {
        guard next != marking || again else { return }
        marking = next
        if loaded {
            view.callAsyncJavaScript(
                SheetHTML.markScript, arguments: next.arguments, in: nil, in: .page)
        }
    }

    private func load(_ content: SheetHTML.Content, in view: WKWebView) {
        loaded = false
        document = content
        view.loadHTMLString(content.document, baseURL: nil)
    }

    private func replace(with content: SheetHTML.Content, in view: WKWebView) {
        view.callAsyncJavaScript(
            Self.replace, arguments: ["style": content.style, "sheets": content.sheets],
            in: nil, in: .page
        ) { [weak self] result in
            guard let self else { return }
            if case .success(let read) = result, let read = read as? Double {
                self.place = read
            } else if content == self.shown, self.loaded {
                // the document could not take them: loaded afresh, at the place last read
                self.load(content, in: view)
            }
        }
    }

    /// Only the app's own page is shown: a link in the core's SVG leads nowhere.
    static func allows(_ type: WKNavigationType, to url: URL?) -> Bool {
        type == .other && url?.scheme == "about"
    }

    func webView(
        _: WKWebView, decidePolicyFor action: WKNavigationAction
    ) async -> WKNavigationActionPolicy {
        Self.allows(action.navigationType, to: action.request.url) ? .allow : .cancel
    }

    func webView(_ view: WKWebView, didFinish _: WKNavigation?) {
        loaded = true
        if place > 0 {
            view.callAsyncJavaScript(
                Self.goToPlace, arguments: ["place": place], in: nil, in: .page)
        }
        if let shown, shown != document {
            replace(with: shown, in: view)  // pages that came while it loaded
        }
        if let marking {
            view.callAsyncJavaScript(
                SheetHTML.markScript, arguments: marking.arguments, in: nil, in: .page)
        }
    }

    func webViewWebContentProcessDidTerminate(_ view: WKWebView) {
        guard let shown else { return }
        load(shown, in: view)
    }
}

/// The sheet's web view: it runs no script of a page's, tells its width in points and a
/// pinch's scale, shows a pinch's picture while the fingers move, leaves the keyboard to the
/// window's controls and offers no menu (its "Reload" would empty a page without an address).
final class SheetWebView: WKWebView {
    /// Told every new width, once.
    var resized: (@MainActor (Double) -> Void)?
    /// Told a pinch's whole scale, once the fingers lift.
    var pinched: (@MainActor (Double) -> Void)?
    /// Told where a click landed: the page and the point on it (`SheetHTML.hitScript`).
    var clicked: (@MainActor (Any?) -> Void)?
    /// Where the mouse went down; a click moves less than `slack` points before it goes up.
    private var downAt: CGPoint?
    static let slack = 4.0
    /// How long a lifted pinch's picture waits for the pages laid out at its size.
    var patience: Duration = .milliseconds(1500)
    private var told = 0.0
    private var gesture = Pinch()
    private var pictured = false  // a pinch's picture is on the page
    private var waiting: Task<Void, Never>?

    /// A pinch's picture (SPEC.md, module `mac-sheet`, scope 3): the shown pages drawn larger
    /// or smaller around the point the pinch began at, until the core's pages replace them.
    static let picture = """
        const body = document.body;
        if (!body.style.transform) {
            body.style.transformOrigin = x + "px " + (y + window.scrollY) + "px";
        }
        body.style.transform = "scale(" + scale + ")";
        return true
        """
    static let noPicture = "document.body.style.transform = \"\"; return true"
    /// The picture's limits; the note size's own are the core's.
    static let pictures = 0.2...5.0

    static func make() -> SheetWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = false
        // nothing of the sheet is kept: no ~/Library/WebKit folder to leave behind
        configuration.websiteDataStore = .nonPersistent()
        let view = SheetWebView(frame: .zero, configuration: configuration)
        view.allowsMagnification = false  // the note size is the core's (View menu, pinch)
        view.allowsBackForwardNavigationGestures = false
        view.unregisterDraggedTypes()
        return view
    }

    /// A song dropped on the sheet is the window's to open, not a page for the web view.
    override func registerForDraggedTypes(_: [NSPasteboard.PasteboardType]) {}

    override var acceptsFirstResponder: Bool { false }

    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        let width = Double(newSize.width)
        guard width > 0, width != told else { return }
        told = width
        resized?(width)
    }

    override func magnify(with event: NSEvent) {
        var point = convert(event.locationInWindow, from: nil)
        if !isFlipped {
            point.y = bounds.height - point.y
        }
        pinch(event.phase, by: Double(event.magnification), at: point)
    }

    /// A step of a trackpad pinch at `point` (from the view's top left): the pages' picture
    /// follows the fingers; the note size changes once, when they lift (the core engraves
    /// anew for it), and the picture stays until those pages come.
    func pinch(_ phase: NSEvent.Phase, by magnification: Double, at point: CGPoint = .zero) {
        if phase.contains(.began) {
            waiting?.cancel()
            gesture.begin()
        }
        gesture.change(by: magnification)
        if phase.contains(.cancelled) {
            gesture.cancel()
            settle()
        } else if phase.contains(.ended) {
            guard let scale = gesture.end() else {
                settle()
                return
            }
            pinched?(scale)
            waiting = Task { [weak self, patience] in
                try? await Task.sleep(for: patience)
                guard !Task.isCancelled else { return }
                self?.settle()  // the core refused: no pages will come
            }
        } else if let scale = gesture.soFar {
            pictured = true
            callAsyncJavaScript(
                Self.picture,
                arguments: [
                    "scale": min(max(scale, Self.pictures.lowerBound), Self.pictures.upperBound),
                    "x": Double(point.x), "y": Double(point.y)
                ], in: nil, in: .page)
        }
    }

    /// Takes a pinch's picture back when no pages will replace it: the pinch was cancelled or
    /// changed nothing, the core answered with the pages already shown, or refused.
    func settle() {
        guard pictured, gesture.soFar == nil else { return }
        waiting?.cancel()
        pictured = false
        callAsyncJavaScript(Self.noPicture, arguments: [:], in: nil, in: .page)
    }

    override func mouseDown(with event: NSEvent) {
        downAt = event.locationInWindow
        super.mouseDown(with: event)
    }

    override func mouseUp(with event: NSEvent) {
        super.mouseUp(with: event)
        let down = downAt
        downAt = nil
        if let point = clickPoint(down: down, up: event.locationInWindow) {
            click(at: point)
        }
    }

    /// Where a click landed, from the view's top left: the mouse went up within `slack`
    /// points of where it went down (in the window), else it was a drag.
    func clickPoint(down: CGPoint?, up: CGPoint) -> CGPoint? {
        guard let down, abs(up.x - down.x) < Self.slack, abs(up.y - down.y) < Self.slack
        else { return nil }
        var point = convert(up, from: nil)
        if !isFlipped {
            point.y = bounds.height - point.y
        }
        return point
    }

    /// A click at `point` (from the view's top left): asks the page which page and point it
    /// landed on and tells `clicked`.
    func click(at point: CGPoint) {
        callAsyncJavaScript(
            SheetHTML.hitScript, arguments: ["x": Double(point.x), "y": Double(point.y)],
            in: nil, in: .page
        ) { [weak self] result in
            if case .success(let answer) = result {
                self?.clicked?(answer)
            }
        }
    }

    override func willOpenMenu(_ menu: NSMenu, with _: NSEvent) {
        menu.removeAllItems()
    }
}
