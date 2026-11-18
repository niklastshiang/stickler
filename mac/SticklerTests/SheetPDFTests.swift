import PDFKit
import SticklerCore
import XCTest

@testable import Stickler

/// The PDF the app writes from the core's A4 pages (SPEC.md, module `mac-shell`, Testing):
/// A4 pages, the title, and the text in its fonts (Leipzig for the tempo mark).
@MainActor
final class SheetPDFTests: XCTestCase {
    /// The core's A4 pages of the groove the Python tests engrave (scripts: tests/app/fakes.py).
    func fixturePages() throws -> A4Pages {
        let url = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: "a4_pages", withExtension: "json"))
        let reply = try Incoming(line: Data(contentsOf: url))
        guard case .reply(let pages) = reply else { throw SheetPDF.Failure.notDrawn }
        return try pages.payload(A4Pages.self)
    }

    func testThePDFHasOneA4PagePerPageAndItsTitle() async throws {
        let pages = try fixturePages()
        let data = try await SheetPDF.make(pages)
        let document = try XCTUnwrap(PDFDocument(data: data))
        XCTAssertEqual(document.pageCount, pages.pages.count)
        let bounds = try XCTUnwrap(document.page(at: 0)).bounds(for: .mediaBox)
        XCTAssertEqual(bounds.width, 595.28, accuracy: 1)
        XCTAssertEqual(bounds.height, 841.89, accuracy: 1)
        XCTAssertEqual(
            document.documentAttributes?[PDFDocumentAttribute.titleAttribute] as? String, "Groove")
        try FileManager.default.createDirectory(
            at: ScreenshotTests.folder, withIntermediateDirectories: true)
        try data.write(to: ScreenshotTests.folder.appendingPathComponent("sheet.pdf"))
    }

    func testThePagesTextIsSetInItsFonts() async throws {
        let page = try XCTUnwrap(try fixturePages().pages.first)
        let single = try await SheetPDF.draw(page, face: try SheetPDF.fontFace())
        let raw = try XCTUnwrap(String(bytes: single, encoding: .isoLatin1))  // a PDF is bytes
        XCTAssertTrue(raw.contains("Leipzig"), "the tempo mark's font is not in the PDF")
        let text = try XCTUnwrap(PDFDocument(data: single)?.page(at: 0)?.string)
        XCTAssertTrue(text.contains("120"), text)  // the tempo mark, next to Leipzig's note
    }
}
