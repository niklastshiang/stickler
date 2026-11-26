namespace Stickler.Core.Tests;

/// <summary>The cases of <c>tests/app/test_playback.py</c> and <c>test_marker.py</c> (and the
/// Mac's <c>TimelineTests</c>): 6 song bars of 2 s, the written bars 1 2 1 2 (a repeated
/// phrase), then 3, then 4.</summary>
[TestClass]
public sealed class TimelineTests
{
    internal static readonly IReadOnlyList<SongBar> SongBars =
    [
        new(0, 2, 1, "Bar 1 of 6"),
        new(2, 4, 2, "Bar 2 of 6"),
        new(4, 6, 1, "Bar 3 of 6"),
        new(6, 8, 2, "Bar 4 of 6"),
        new(8, 10, 3, "Bar 5 of 6"),
        new(10, 12, 4, "Bar 6 of 6"),
    ];

    private static SheetPage Page(int[] bars, double width = 100) =>
        new("", width, 50, [.. bars.Select((bar, place) => new BarBox(bar, place * 20, 10, 20, 30))]);

    [TestMethod]
    public void TheSoundingBarIsTheLastOneStartedBeforeTheEnd()
    {
        Assert.IsNull(Timeline.Index(SongBars, -0.1));
        Assert.AreEqual(0, Timeline.Index(SongBars, 0));
        Assert.AreEqual(1, Timeline.Index(SongBars, 3.99));
        Assert.AreEqual(2, Timeline.Index(SongBars, 4));
        Assert.AreEqual(5, Timeline.Index(SongBars, 99));
        Assert.IsNull(Timeline.Index([], 1));
        Assert.AreEqual(1, Timeline.Written(SongBars, 0));
        Assert.AreEqual(1, Timeline.Written(SongBars, 5)); // the repeat's second pass
        Assert.AreEqual(2, Timeline.Written(SongBars, 3.99));
        Assert.AreEqual(1, Timeline.Written(SongBars, 4));
        Assert.AreEqual(4, Timeline.Written(SongBars, 11.9));
        Assert.IsNull(Timeline.Written(SongBars, -0.1));
        Assert.IsNull(Timeline.Written(SongBars, 12)); // after the last bar
        Assert.IsNull(Timeline.Written([], 1));
    }

    [TestMethod]
    public void TheLabelAndTheClockAreThePythonOnes()
    {
        Assert.AreEqual("Bar 3 of 6", Timeline.Label(SongBars, 5));
        Assert.AreEqual("Bar 6 of 6", Timeline.Label(SongBars, 99));
        Assert.AreEqual("Bar 1 of 6", Timeline.Label(SongBars, -1));
        Assert.AreEqual("", Timeline.Label([], 1));
        Assert.AreEqual("0:06", Timeline.Clock(6.4));
        Assert.AreEqual("4:06", Timeline.Clock(246));
        Assert.AreEqual("1:02:05", Timeline.Clock(3725));
        Assert.AreEqual("0:00", Timeline.Clock(-3));
        Assert.AreEqual("0:00", Timeline.Clock(double.NaN));
        Assert.AreEqual("0:00", Timeline.Clock(double.PositiveInfinity));
    }

    [TestMethod]
    public void ABarWithoutItsOwnRectangleIsMarkedByTheOneBefore()
    {
        IReadOnlyList<SheetPage> pages = [Page([1, 2, 3]), Page([5, 7])]; // 4 and 6 inside multi-measure rests
        Assert.AreEqual(new Marker.Mark(0, pages[0].Bars[1]), Marker.Locate(2, pages));
        Assert.AreEqual(new Marker.Mark(1, pages[1].Bars[0]), Marker.Locate(5, pages));
        Assert.AreEqual(Marker.Locate(3, pages), Marker.Locate(4, pages));
        Assert.AreEqual(Marker.Locate(5, pages), Marker.Locate(6, pages));
        Assert.IsNull(Marker.Locate(-5, pages));
        Assert.IsNull(Marker.Locate(1, []));
    }

    [TestMethod]
    public void AClickFindsTheBarUnderIt()
    {
        var first = Page([1, 2, 3]);
        Assert.AreEqual(2, Marker.BarAt(30, 25, first));
        Assert.AreEqual(1, Marker.BarAt(20, 10, first)); // the edge belongs to the first
        Assert.IsNull(Marker.BarAt(-10, -10, first));
        Assert.IsNull(Marker.BarAt(30, 45, first));
    }
}
