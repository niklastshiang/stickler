import Foundation
import Testing

@testable import SticklerCore

/// Lines a newer or broken core could send: kept or refused, never misread.

@Test func aStateOfAnUnknownKindIsKeptWithItsName() throws {
    let line = #"{"event": "state", "seq": 3, "state": {"kind": "listening", "can_open": true}}"#
    guard case .event(3, .state(let state)) = try Incoming(line: Data(line.utf8)) else {
        Issue.record("not a state event")
        return
    }
    #expect(state.screen == .unknown(kind: "listening") && state.screen.kind == "listening")
    #expect(state.can == Abilities(open: true))
    let encoded = try object(encoding: state)
    let disabled = ["cancel", "retry", "close", "export", "agree", "not_now", "retry_setup",
                    "remove_models"].map { "\"can_\($0)\": false" }.joined(separator: ", ")
    #expect(encoded == (try object(#"{"kind": "listening", "can_open": true, "# + disabled + "}")))
}

@Test func anUnknownEventIsKeptWithItsName() throws {
    let line = #"{"event": "progress", "seq": 4}"#
    #expect(try Incoming(line: Data(line.utf8)) == .event(seq: 4, .unknown(name: "progress")))
}

@Test func anUnknownErrorCodeIsKept() throws {
    let line = #"{"id": 2, "ok": false, "error": {"code": "busy", "message": "Later."}}"#
    guard case .reply(let reply) = try Incoming(line: Data(line.utf8)) else {
        Issue.record("not a reply")
        return
    }
    #expect(reply.error?.code == .other("busy") && reply.error?.code.name == "busy")
    let encoded = try object(encoding: reply.error)
    #expect(encoded == (try object(#"{"code": "busy", "message": "Later."}"#)))
}

@Test func aBadRequestHasNoId() throws {
    let line = #"{"id": null, "ok": false, "error": {"code": "bad_request", "message": "No."}}"#
    guard case .reply(let reply) = try Incoming(line: Data(line.utf8)) else {
        Issue.record("not a reply")
        return
    }
    #expect(reply.id == nil && reply.error?.code == .badRequest)
}

@Test func aFailedReplyWithoutAnErrorIsStillAFailure() throws {
    guard case .reply(let reply) = try Incoming(line: Data(#"{"id": 7, "ok": false}"#.utf8)) else {
        Issue.record("not a reply")
        return
    }
    #expect(!reply.ok && reply.error?.code == .internal)
}

@Test(arguments: [
    "not json", #"["a list"]"#, #"{"seq": 1}"#, #"{"event": 3}"#
])
func aLineThatIsNeitherEventNorReplyIsRefused(line: String) {
    #expect(throws: Incoming.Unreadable(Data(line.utf8))) { try Incoming(line: Data(line.utf8)) }
}

@Test func aKnownEventWithBrokenFieldsIsAnError() {
    #expect(throws: DecodingError.self) {
        try Incoming(line: Data(#"{"event": "notice", "seq": 1, "text": 5}"#.utf8))
    }
}

@Test func theEmptyStateAllowsOnlyOpening() {
    #expect(AppState.empty.screen == .empty && AppState.empty.can == Abilities(open: true))
}

@Test func aLineThatIsNotUTF8IsRefusedAndSaysSo() {
    let bytes = Data([0x7B, 0xFF, 0xFE, 0x7D])  // "{", two invalid bytes, "}"
    #expect(throws: Incoming.Unreadable(bytes)) { try Incoming(line: bytes) }
    #expect(Incoming.Unreadable(bytes).line == "(not UTF-8)")
}
