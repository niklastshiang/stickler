import Foundation
import Testing

@testable import SticklerCore

/// `docs/bridge.md` is the contract (SPEC.md, module `mac-shell`, task 108): every example line
/// decodes, and encodes back to the same JSON, so a field Swift does not know fails here.

/// The JSON lines of each ```json block, with the heading above it.
func documentExamples() throws -> [(heading: String, lines: [String])] {
    var blocks: [(String, [String])] = []
    var heading = ""
    var inside = false
    for line in try bridgeDocument().split(separator: "\n", omittingEmptySubsequences: false) {
        if line.hasPrefix("#") {
            heading = line.trimmingCharacters(in: CharacterSet(charactersIn: "# `"))
        } else if line == "```json" {
            inside = true
            blocks.append((heading, []))
        } else if line == "```" {
            inside = false
        } else if inside {
            blocks[blocks.count - 1].1.append(String(line))
        }
    }
    return blocks
}

func object(_ text: String) throws -> NSDictionary {
    try #require(try JSONSerialization.jsonObject(with: Data(text.utf8)) as? NSDictionary)
}

func object(encoding value: some Encodable) throws -> NSDictionary {
    try #require(
        try JSONSerialization.jsonObject(with: LineCoding.encoder().encode(value)) as? NSDictionary
    )
}

func without(_ dict: NSDictionary, _ keys: String...) -> NSDictionary {
    let copy = NSMutableDictionary()
    for (key, value) in dict {
        if let key = key as? String, !keys.contains(key) {
            copy.setObject(value, forKey: key as NSString)
        }
    }
    return copy
}

/// The section names under a top-level heading (`## States` → `### empty`, …).
func documentSections(under top: String) throws -> Set<String> {
    var names: Set<String> = []
    var within = false
    for line in try bridgeDocument().split(separator: "\n") {
        if line.hasPrefix("## ") {
            within = line == "## \(top)"
        } else if within, line.hasPrefix("### ") {
            names.insert(line.dropFirst(4).trimmingCharacters(in: CharacterSet(charactersIn: "`")))
        }
    }
    return names
}

@Test func everyStateDecodesToItsKindAndBackToTheSameFields() throws {
    let states = try documentExamples().flatMap(\.lines).filter { $0.hasPrefix(#"{"kind""#) }
    #expect(states.count == 8)
    var kinds: Set<String> = []
    for line in states {
        let state = try LineCoding.decoder().decode(AppState.self, from: Data(line.utf8))
        if case .unknown(let kind) = state.screen {
            Issue.record("unknown kind \(kind)")
        }
        kinds.insert(state.screen.kind)
        let encoded = try object(encoding: state), documented = try object(line)
        #expect(encoded == documented, "\(state.screen.kind)")
    }
    #expect(kinds == (try documentSections(under: "States")))
}

@Test func everyEventDecodesWithItsSequenceNumber() throws {
    let events = try documentExamples().flatMap(\.lines).filter { $0.hasPrefix(#"{"event""#) }
    var names: Set<String> = []
    for line in events {
        let dict = try object(line)
        switch try Incoming(line: Data(line.utf8)) {
        case .hello(let hello):
            names.insert("hello")
            #expect(hello.protocol == BridgeProtocol.version)
            let encoded = try object(encoding: hello)
            #expect(encoded == without(dict, "event"))
        case .event(let seq, let event):
            #expect(seq == dict["seq"] as? Int)
            switch event {
            case .state(let state):
                names.insert("state")
                let encoded = try object(encoding: state)
                #expect(encoded == dict["state"] as? NSDictionary)
            case .recent(let rows):
                names.insert("recent")
                let encoded = try JSONSerialization.jsonObject(
                    with: LineCoding.encoder().encode(rows)) as? NSArray
                #expect(encoded == dict["rows"] as? NSArray)
                #expect(rows.first?.title == "Eye of the Tiger")
            case .notice(let notice):
                names.insert("notice")
                let encoded = try object(encoding: notice)
                #expect(encoded == without(dict, "event", "seq"))
            case .unknown(let name):
                Issue.record("unknown event \(name)")
            }
        case .reply:
            Issue.record("an event read as a reply: \(line)")
        }
    }
    #expect(names == (try documentSections(under: "Events")))
}

/// The commands as the documents' examples write them.
let sampleCommands: [Command] = [
    .start, .agree, .notNow, .retrySetup, .open(path: "/Users/me/Music/Eye of the Tiger.flac"),
    .cancel, .retry, .close, .pages(width: 800, zoom: 1.25), .a4Pages,
    .exportMusicXML(dest: "/Users/me/Desktop/Eye of the Tiger.musicxml"), .drumTrackCost,
    .exportDrumTrack(dest: "/Users/me/Desktop/Eye of the Tiger (drums).flac"),
    .forgetRecent(path: "/Users/me/Music/Gone.flac"), .settings, .setZoom(1.5), .zoomIn,
    .zoomOut, .actualSize, .removalSizes, .removeModels(everything: false),
    .backUp(dest: "/Users/me/Documents/Stickler Backup 2026-11-22.zip"),
    .backupSummary(src: "/Users/me/Documents/Stickler Backup 2026-11-22.zip"),
    .restore(src: "/Users/me/Documents/Stickler Backup 2026-11-22.zip"), .uninstallSizes,
    .uninstall(everything: false), .quit
]

@Test func everyCommandIsWrittenAsTheDocumentShowsIt() throws {
    let commands = try documentExamples().flatMap(\.lines).filter { $0.contains(#""cmd""#) }
    #expect(Set(sampleCommands.map(\.name)) == (try documentSections(under: "Commands")))
    for line in commands {
        let dict = try object(line)
        let name = try #require(dict["cmd"] as? String)
        let command = try #require(sampleCommands.first { $0.name == name })
        let id = try #require(dict["id"] as? Int)
        let written = try #require(
            try JSONSerialization.jsonObject(with: command.line(id: id)) as? NSDictionary)
        #expect(written == dict, "\(name)")
    }
}

@Test func aCommandIsOneLine() throws {
    let line = try Command.open(path: "/a/b c/€.flac").line(id: 3)
    #expect(!line.contains(UInt8(ascii: "\n")))
    let text = try #require(String(bytes: line, encoding: .utf8))
    #expect(text.contains(#""path":"/a/b c/€.flac""#))
    let pages = try Command.pages(width: 640, zoom: nil).line(id: 4)
    let stored = try object(try #require(String(bytes: pages, encoding: .utf8)))
    #expect(stored["zoom"] == nil)  // the stored note size
}

/// The payload type of each command whose reply has more than `ok`.
func payloadMatches(_ command: String, _ line: Data) throws -> NSDictionary? {
    let reply: Reply
    guard case .reply(let read) = try Incoming(line: line) else { return nil }
    reply = read
    switch command {
    case "pages": return try object(encoding: reply.payload(Pages.self))
    case "a4_pages": return try object(encoding: reply.payload(A4Pages.self))
    case "drum_track_cost": return try object(encoding: reply.payload(DrumTrackCost.self))
    case "settings": return try object(encoding: reply.payload(Settings.self))
    case "set_zoom", "zoom_in", "zoom_out", "actual_size":
        return try object(encoding: reply.payload(Zoom.self))
    case "removal_sizes": return try object(encoding: reply.payload(RemovalSizes.self))
    default: return NSDictionary()
    }
}

@Test func everyReplyDecodesWithItsFields() throws {
    for block in try documentExamples() where block.lines.count == 2 {
        guard block.lines[0].contains(#""cmd""#) else { continue }
        let command = try #require(try object(block.lines[0])["cmd"] as? String)
        let line = Data(block.lines[1].utf8)
        guard case .reply(let reply) = try Incoming(line: line) else {
            Issue.record("not a reply: \(block.lines[1])")
            continue
        }
        let id = try object(block.lines[0])["id"] as? Int
        #expect(reply.ok && reply.id == id)
        let fields = try #require(try payloadMatches(command, line))
        let documented = without(try object(block.lines[1]), "id", "ok")
        #expect(fields == documented, "\(command)")
    }
}

@Test func anErrorReplyCarriesItsCodeAndMessage() throws {
    let lines = try documentExamples().first { $0.heading == "Lines and lifetime" }?.lines ?? []
    #expect(lines.count == 2)
    guard case .reply(let failed) = try Incoming(line: Data(lines[1].utf8)) else {
        Issue.record("not a reply")
        return
    }
    #expect(!failed.ok && failed.id == 5)
    #expect(failed.error == BridgeError(code: .notNow, message: "This is not possible right now."))
}

@Test func everyDocumentedErrorCodeIsKnown() throws {
    let section = try bridgeDocument().components(separatedBy: "\n## Errors\n")[1]
        .components(separatedBy: "\n## ")[0]
    let codes = section.split(separator: "\n")
        .filter { $0.hasPrefix("| `") }
        .compactMap { $0.split(separator: "`").dropFirst().first.map(String.init) }
    #expect(codes.count == 5)
    for name in codes {
        let code = try LineCoding.decoder().decode(
            BridgeError.Code.self, from: Data("\"\(name)\"".utf8))
        #expect(code != .other(name), "\(name)")
        #expect(code.name == name)
    }
}
