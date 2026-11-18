import Foundation
import Testing

@testable import SticklerCore

@Test func aLineCutAcrossReadsComesOutWhole() {
    var splitter = LineSplitter()
    #expect(splitter.feed(Data(#"{"a": "#.utf8)).isEmpty)
    #expect(splitter.feed(Data("1}\n{\"b\"".utf8)) == [Data(#"{"a": 1}"#.utf8)])
    #expect(splitter.feed(Data(": 2}\n\n{}\n".utf8)) == [Data(#"{"b": 2}"#.utf8), Data("{}".utf8)])
    #expect(splitter.finish() == nil)
}

@Test func aLastLineWithoutNewlineIsKeptAtTheEnd() {
    var splitter = LineSplitter()
    #expect(splitter.feed(Data("one\ntwo".utf8)) == [Data("one".utf8)])
    #expect(splitter.finish() == Data("two".utf8))
    #expect(splitter.finish() == nil)
}

@Test func theTailKeepsTheNewestLines() {
    var tail = Tail(limit: 3)
    tail.feed(Data("a\nb\nc\nd".utf8))
    #expect(tail.lines == ["a", "b", "c"])  // "d" waits for its newline
    tail.feed(Data([0x0A, 0xFF, 0x0A]))
    tail.feed(Data("last".utf8))
    tail.finish()
    #expect(tail.lines == ["d", "(not UTF-8)", "last"])
}
