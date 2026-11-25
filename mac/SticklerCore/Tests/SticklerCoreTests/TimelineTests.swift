import Foundation
import Testing

@testable import SticklerCore

// The cases of tests/app/test_playback.py and test_marker.py: 6 song bars of 2 s, the written
// bars 1 2 1 2 (a repeated phrase), then 3, then 4.
let songBars = [
    SongBar(start: 0, end: 2, bar: 1, label: "Bar 1 of 6"),
    SongBar(start: 2, end: 4, bar: 2, label: "Bar 2 of 6"),
    SongBar(start: 4, end: 6, bar: 1, label: "Bar 3 of 6"),
    SongBar(start: 6, end: 8, bar: 2, label: "Bar 4 of 6"),
    SongBar(start: 8, end: 10, bar: 3, label: "Bar 5 of 6"),
    SongBar(start: 10, end: 12, bar: 4, label: "Bar 6 of 6")
]

@Suite struct TheLookups {
    @Test func theSoundingBarIsTheLastOneStartedBeforeTheEnd() {
        #expect(Timeline.index(songBars, at: -0.1) == nil)
        #expect(Timeline.index(songBars, at: 0) == 0)
        #expect(Timeline.index(songBars, at: 3.99) == 1)
        #expect(Timeline.index(songBars, at: 4) == 2)
        #expect(Timeline.index(songBars, at: 99) == 5)
        #expect(Timeline.index([], at: 1) == nil)
        #expect(Timeline.written(songBars, at: 0) == 1)
        #expect(Timeline.written(songBars, at: 5) == 1)  // the repeat's second pass
        #expect(Timeline.written(songBars, at: 11.9) == 4)
        #expect(Timeline.written(songBars, at: -0.1) == nil)
        #expect(Timeline.written(songBars, at: 12) == nil)  // after the last bar
        #expect(Timeline.written([], at: 1) == nil)
    }

    @Test func theLabelAndTheClockAreThePythonOnes() {
        #expect(Timeline.label(songBars, at: 5) == "Bar 3 of 6")
        #expect(Timeline.label(songBars, at: 99) == "Bar 6 of 6")
        #expect(Timeline.label(songBars, at: -1) == "Bar 1 of 6")
        #expect(Timeline.label([], at: 1) == "")
        #expect(Timeline.clock(6.4) == "0:06")
        #expect(Timeline.clock(246) == "4:06")
        #expect(Timeline.clock(3725) == "1:02:05")
        #expect(Timeline.clock(-3) == "0:00")
        #expect(Timeline.clock(.nan) == "0:00")
    }

    func page(_ bars: [Int], width: Double = 100) -> Page {
        Page(
            svg: "", width: width, height: 50,
            bars: bars.enumerated().map { place, bar in
                BarBox(bar: bar, x: Double(place) * 20, y: 10, width: 20, height: 30)
            })
    }

    @Test func aBarWithoutItsOwnRectangleIsMarkedByTheOneBefore() {
        let pages = [page([1, 2, 3]), page([5, 7])]  // 4 and 6 inside multi-measure rests
        #expect(Marker.locate(2, in: pages) == Marker.Mark(page: 0, box: pages[0].bars[1]))
        #expect(Marker.locate(5, in: pages) == Marker.Mark(page: 1, box: pages[1].bars[0]))
        #expect(Marker.locate(4, in: pages) == Marker.locate(3, in: pages))
        #expect(Marker.locate(6, in: pages) == Marker.locate(5, in: pages))
        #expect(Marker.locate(-5, in: pages) == nil)
        #expect(Marker.locate(1, in: []) == nil)
    }

    @Test func aClickFindsTheBarUnderIt() {
        let first = page([1, 2, 3])
        #expect(Marker.bar(atX: 30, y: 25, on: first) == 2)
        #expect(Marker.bar(atX: 20, y: 10, on: first) == 1)  // the edge belongs to the first
        #expect(Marker.bar(atX: -10, y: -10, on: first) == nil)
        #expect(Marker.bar(atX: 30, y: 45, on: first) == nil)
    }
}
