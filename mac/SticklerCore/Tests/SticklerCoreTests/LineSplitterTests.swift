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

@Test func theEndSaysHowTheCoreEnded() {
    let ends: [(CoreEnd.Reason, String)] = [
        (.exited(3), "The core exited with status 3."),
        (.signalled(9), "The core was ended by signal 9."),
        (.wrongProtocol(2), "The core speaks protocol 2; this app speaks 1."),
        (.notStarted("no uv"), "The core could not be started: no uv")
    ]
    for (reason, summary) in ends {
        #expect(CoreEnd(reason: reason, details: []).summary == summary)
    }
    let end = CoreEnd(reason: .exited(1), details: ["Traceback", "MemoryError"])
    #expect(end.technicalDetails == "The core exited with status 1.\nTraceback\nMemoryError")
}

@Test func theSavePanelsProposeTheGTKAppsNames() {
    #expect(ExportName.musicXML("/m/Eye of the Tiger.flac") == "Eye of the Tiger.musicxml")
    #expect(ExportName.pdf("/m/Eye of the Tiger.flac") == "Eye of the Tiger.pdf")
    #expect(ExportName.base(of: "/m/ two words .mp3") == "two words")
    #expect(ExportName.base(of: "/m/ .flac") == "Stickler")
}
