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
/// the same page is loaded again instead of leaving the sheet blank.
@MainActor
final class SheetLoad: NSObject, WKNavigationDelegate {
    private(set) var shown: String?

    func show(_ html: String, in view: WKWebView) {
        guard html != shown else { return }
        shown = html
        view.loadHTMLString(html, baseURL: nil)
    }

    func webViewWebContentProcessDidTerminate(_ view: WKWebView) {
        guard let html = shown else { return }
        shown = nil
        show(html, in: view)
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
        return view
    }

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
