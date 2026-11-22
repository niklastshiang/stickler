import SticklerCore
import XCTest

@testable import Stickler

/// Stickler › "Uninstall Stickler…" (`Uninstalling`), with the reader's answers from
/// `FakeAsking`, the core played by `ScriptedCore`, and the Bin and quitting replaced.
extension LogicTests {
    static let uninstallSizes = #""ok": true, "keep": 2, "everything": 3, "#
        + #""keep_text": "Frees 2 B.", "everything_text": "Frees 3 B.""#

    private func uninstalling(at bundle: String) -> (trashed: () -> [URL], quit: () -> Int) {
        var trashed: [URL] = []
        var quits = 0
        Uninstalling.bundle = URL(fileURLWithPath: bundle)
        Uninstalling.trash = { trashed.append($0) }
        Uninstalling.quit = { quits += 1 }
        return ({ trashed }, { quits })
    }

    func testUninstallingRemovesTheDataThenTheBundleAndQuits() async throws {
        let seen = uninstalling(at: "/Applications/Stickler.app")
        let (model, core) = try await model(
            replies: ["uninstall_sizes": Self.uninstallSizes, "uninstall": #""ok": true"#])
        asking.uninstallAnswer = false
        await Uninstalling.ask(model)
        XCTAssertEqual(asking.uninstallSizes.last?.keepText, "Frees 2 B.")
        XCTAssertTrue(core.sent.contains(.uninstall(everything: false)))
        XCTAssertEqual(seen.trashed(), [URL(fileURLWithPath: "/Applications/Stickler.app")])
        XCTAssertEqual(seen.quit(), 1)
        Removal.everything = false
    }

    func testAKeptAppSendsNothingAndStays() async throws {
        let seen = uninstalling(at: "/Applications/Stickler.app")
        let (model, core) = try await model(replies: ["uninstall_sizes": Self.uninstallSizes])
        asking.uninstallAnswer = nil
        await Uninstalling.ask(model)
        XCTAssertFalse(core.sent.contains { $0.name == "uninstall" })
        XCTAssertEqual(seen.quit(), 0)
    }

    func testARefusedUninstallKeepsTheBundle() async throws {
        let seen = uninstalling(at: "/Applications/Stickler.app")
        let (model, _) = try await model(replies: [
            "uninstall_sizes": Self.uninstallSizes,
            "uninstall": #""ok": false, "error": {"code": "not_now", "message": "Not now."}"#
        ])
        asking.uninstallAnswer = true
        await Uninstalling.ask(model)
        XCTAssertTrue(seen.trashed().isEmpty)
        XCTAssertEqual(seen.quit(), 0)
    }

    func testATranslocatedAppShowsTheStepsInstead() async throws {
        let seen = uninstalling(at: "/private/var/folders/x/AppTranslocation/1/d/Stickler.app")
        let (model, core) = try await model(replies: ["uninstall_sizes": Self.uninstallSizes])
        asking.uninstallAnswer = false
        await Uninstalling.ask(model)
        XCTAssertEqual(asking.told.count, 1)
        XCTAssertFalse(core.sent.contains { $0.name == "uninstall" })
        XCTAssertTrue(seen.trashed().isEmpty)
    }
}
