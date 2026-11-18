import PDFKit
import SticklerCore
import WebKit

/// The PDF the Mac app writes from the core's A4 pages (`a4_pages`), as `ui/pdf.py` does with
/// cairo for GTK: each page's SVG drawn by WebKit onto an A4 page, the pages joined by PDFKit.
@MainActor
enum SheetPDF {
    static let paper = CGSize(width: 595.28, height: 841.89)  // 210 × 297 mm in points

    enum Failure: Error {
        case noFont, notDrawn
    }

    /// The Leipzig font as a CSS source: WebKit draws in a process of its own, which sees no
    /// font the app registers, and the tempo mark is set in Leipzig.
    static func fontFace() throws -> String {
        guard let url = Bundle.main.url(forResource: "Leipzig", withExtension: "ttf") else {
            throw Failure.noFont
        }
        let font = try Data(contentsOf: url).base64EncodedString()
        return "@font-face { font-family: Leipzig; src: url(data:font/ttf;base64,\(font)); }"
    }

    static func make(_ pages: A4Pages) async throws -> Data {
        let face = try fontFace()
        let document = PDFDocument()
        for page in pages.pages {
            let single = try await draw(page, face: face)
            guard let drawn = PDFDocument(data: single)?.page(at: 0) else {
                throw Failure.notDrawn
            }
            document.insert(drawn, at: document.pageCount)
        }
        document.documentAttributes = [
            PDFDocumentAttribute.titleAttribute: pages.title,
            PDFDocumentAttribute.creatorAttribute: "Stickler"
        ]
        guard let data = document.dataRepresentation() else { throw Failure.notDrawn }
        return data
    }

    /// One page as a one-page PDF, scaled from its pixels to A4.
    static func draw(_ page: Page, face: String) async throws -> Data {
        let scale = paper.width / page.width
        let html = """
            <!doctype html><html><head><meta charset="utf-8"><style>
            \(face)
            html, body { margin: 0; padding: 0; background: white; }
            #page { transform: scale(\(scale)); transform-origin: 0 0; }
            </style></head><body><div id="page">\(page.svg)</div></body></html>
            """
        let view = WKWebView(frame: CGRect(origin: .zero, size: paper))
        let loaded = PageLoad()
        view.navigationDelegate = loaded
        view.loadHTMLString(html, baseURL: nil)
        try await loaded.finished()
        _ = try await view.callAsyncJavaScript(
            "await document.fonts.ready; return document.fonts.size", contentWorld: .page)
        let configuration = WKPDFConfiguration()
        configuration.rect = CGRect(origin: .zero, size: paper)
        return try await view.pdf(configuration: configuration)
    }
}

/// Waits for a web view's page to load.
@MainActor
final class PageLoad: NSObject, WKNavigationDelegate {
    private var waiting: CheckedContinuation<Void, any Error>?
    private var outcome: Result<Void, any Error>?

    func finished() async throws {
        if let outcome {
            return try outcome.get()
        }
        try await withCheckedThrowingContinuation { waiting = $0 }
    }

    func webView(_: WKWebView, didFinish _: WKNavigation?) {
        end(.success(()))
    }

    func webView(_: WKWebView, didFail _: WKNavigation?, withError error: any Error) {
        end(.failure(error))
    }

    func webView(
        _: WKWebView, didFailProvisionalNavigation _: WKNavigation?, withError error: any Error
    ) {
        end(.failure(error))
    }

    private func end(_ result: Result<Void, any Error>) {
        outcome = result
        waiting?.resume(with: result)
        waiting = nil
    }
}
