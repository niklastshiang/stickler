import Foundation
import Testing

@testable import SticklerCore

/// `docs/bridge.md`, read from the checkout this package lives in.
func bridgeDocument() throws -> String {
    let root = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()  // SticklerCoreTests
        .deletingLastPathComponent()  // Tests
        .deletingLastPathComponent()  // SticklerCore
        .deletingLastPathComponent()  // mac
        .deletingLastPathComponent()
    return try String(contentsOf: root.appendingPathComponent("docs/bridge.md"), encoding: .utf8)
}

@Test func theClientSpeaksTheProtocolTheDocumentDescribes() throws {
    struct Hello: Decodable {
        let event: String
        let `protocol`: Int
    }
    let line = try #require(
        try bridgeDocument().split(separator: "\n").first { $0.contains(#""event": "hello""#) }
    )
    let hello = try JSONDecoder().decode(Hello.self, from: Data(line.utf8))
    #expect(hello.event == "hello")
    #expect(hello.protocol == BridgeProtocol.version)
    #expect(BridgeProtocol.speaks(hello.protocol))
}

@Test func anotherProtocolVersionIsRefused() {
    #expect(!BridgeProtocol.speaks(BridgeProtocol.version + 1))
    #expect(!BridgeProtocol.speaks(0))
}
