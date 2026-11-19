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
            html: SheetHTML.document(model.sheet.pages, dark: dark), dark: dark,
            resized: { width in
                if let pages = SheetHTML.pagesWidth(in: width) {
                    model.sheet.resize(to: pages)
                }
            },
            pinched: { scale in model.sheet.pinched(by: scale) })
        // one picture to VoiceOver, not the notes' hundreds of shapes
        .accessibilityElement(children: .ignore)
        .accessibilityAddTraits(.isImage)
        .accessibilityLabel(
            Text(verbatim: SheetHTML.label(title: model.title, pages: model.sheet.pages.count)))
    }
}

/// The web view in SwiftUI: it shows `html` and loads it again only when it changes.
struct SheetWeb: NSViewRepresentable {
    let html: String
    let dark: Bool
    let resized: @MainActor (Double) -> Void
    let pinched: @MainActor (Double) -> Void

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
        let desk = SheetHTML.desk(dark: dark)
        view.underPageBackgroundColor = NSColor(
            srgbRed: CGFloat(desk.red) / 255, green: CGFloat(desk.green) / 255,
            blue: CGFloat(desk.blue) / 255, alpha: 1)
        context.coordinator.show(html, in: view)
    }
}

/// What the web view shows now. A page is loaded once; when WebKit's drawing process dies,
/// the same page is loaded again instead of leaving the sheet blank. Pages laid out again (a
/// resize, another note size, the other appearance) are shown where the reader was: as far
/// down the new page as they had scrolled down the old one.
@MainActor
final class SheetLoad: NSObject, WKNavigationDelegate {
    private(set) var shown: String?
    /// How far down the reader was: 0 the top, 1 the page's whole height.
    private var place = 0.0
    private var turn = 0  // the newest page's number; an older one still reading is dropped

    /// The app's own script, which runs although the page's are off.
    static let readPlace =
        "return window.scrollY / Math.max(1, document.documentElement.scrollHeight)"
    static let goToPlace =
        "window.scrollTo(0, place * document.documentElement.scrollHeight); return true"

    func show(_ html: String, in view: WKWebView) {
        guard html != shown else { return }
        let replaces = shown != nil
        shown = html
        turn += 1
        guard replaces else {
            view.loadHTMLString(html, baseURL: nil)
            return
        }
        let mine = turn
        Task {
            // a page still loading has not been scrolled to its place yet: the last one holds
            if !view.isLoading {
                let read = try? await view.callAsyncJavaScript(
                    Self.readPlace, contentWorld: .page)
                place = read as? Double ?? place
            }
            guard mine == turn else { return }
            view.loadHTMLString(html, baseURL: nil)
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
        guard place > 0 else { return }
        let place = place
        Task {
            _ = try? await view.callAsyncJavaScript(
                Self.goToPlace, arguments: ["place": place], contentWorld: .page)
        }
    }

    func webViewWebContentProcessDidTerminate(_ view: WKWebView) {
        guard let html = shown else { return }
        turn += 1
        view.loadHTMLString(html, baseURL: nil)
    }
}

/// The sheet's web view: it runs no script, tells its width in points and a pinch's scale,
/// leaves the keyboard to the window's controls and offers no menu (its "Reload" would empty
/// a page without an address).
final class SheetWebView: WKWebView {
    /// Told every new width, once.
    var resized: (@MainActor (Double) -> Void)?
    /// Told a pinch's whole scale, once the fingers lift.
    var pinched: (@MainActor (Double) -> Void)?
    private var told = 0.0
    private var gesture = Pinch()

    static func make() -> SheetWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = false
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
        pinch(event.phase, by: Double(event.magnification))
    }

    /// A step of a trackpad pinch: the note size changes once, when the fingers lift (the
    /// core engraves anew for it), not while they move.
    func pinch(_ phase: NSEvent.Phase, by magnification: Double) {
        if phase.contains(.began) {
            gesture.begin()
        }
        gesture.change(by: magnification)
        if phase.contains(.cancelled) {
            gesture.cancel()
        } else if phase.contains(.ended), let scale = gesture.end() {
            pinched?(scale)
        }
    }

    override func willOpenMenu(_ menu: NSMenu, with _: NSEvent) {
        menu.removeAllItems()
    }
}
