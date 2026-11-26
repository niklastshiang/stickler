namespace Stickler.Core;

/// <summary>What to hear (design screen W10's segmented picker): the song, the detected hits as
/// clicks, or both. The wire names are <c>song</c>, <c>hits</c> and <c>both</c>.</summary>
public enum Hear
{
    Song,
    Hits,
    Both,
}

/// <summary>The lookups the controls and the marker make 20 times a second (SPEC.md, "Mac
/// playback", "Where each decision lives"): a round trip to the core per frame would wait behind
/// <c>pages</c>. Each mirrors a function of <c>stickler_app</c> and the Mac's <c>Timeline</c>; the
/// bars and their texts are the core's.</summary>
public static class Timeline
{
    /// <summary>The index of the song bar started by <paramref name="seconds"/>: the last one whose
    /// start is not later; <c>null</c> before the first.</summary>
    public static int? Index(IReadOnlyList<SongBar> bars, double seconds)
    {
        var low = 0;
        var high = bars.Count;
        while (low < high)
        {
            var middle = (low + high) / 2;
            if (bars[middle].Start <= seconds)
            {
                low = middle + 1;
            }
            else
            {
                high = middle;
            }
        }
        return low > 0 ? low - 1 : null;
    }

    /// <summary>The written bar sounding at <paramref name="seconds"/> (<c>marker.written_at</c>);
    /// <c>null</c> before the first bar and from the last one's end.</summary>
    public static int? Written(IReadOnlyList<SongBar> bars, double seconds)
    {
        if (Index(bars, seconds) is not { } sounding || seconds >= bars[sounding].End)
        {
            return null;
        }
        return bars[sounding].Bar;
    }

    /// <summary>"Bar 3 of 110" at <paramref name="seconds"/> (<c>playback.bar_label</c>): before the
    /// first bar the first one's, after the last the last one's; nothing without bars.</summary>
    public static string Label(IReadOnlyList<SongBar> bars, double seconds) =>
        bars.Count == 0 ? "" : bars[Index(bars, seconds) ?? 0].Label;

    /// <summary>The time as the controls show it (<c>playback.clock</c>): "0:06", "4:06", "1:02:05".</summary>
    public static string Clock(double seconds)
    {
        var whole = double.IsFinite(seconds) ? (long)Math.Max(seconds, 0) : 0;
        var hours = whole / 3600;
        var minutes = whole % 3600 / 60;
        var rest = whole % 60;
        return hours > 0 ? $"{hours}:{minutes:00}:{rest:00}" : $"{minutes}:{rest:00}";
    }
}

/// <summary>Where the sheet marks a bar and which bar a click is on (<c>stickler_app.marker</c>).</summary>
public static class Marker
{
    /// <summary>A written bar's place: the page it is on and its rectangle there.</summary>
    public sealed record Mark(int Page, BarBox Box);

    /// <summary>The page and rectangle that mark written bar <paramref name="written"/>
    /// (<c>marker.locate</c>): a bar without a rectangle of its own (inside a multi-measure rest)
    /// is shown by the nearest engraved bar before it. <c>null</c> when none comes before it.</summary>
    public static Mark? Locate(int written, IReadOnlyList<SheetPage> pages)
    {
        Mark? found = null;
        for (var number = 0; number < pages.Count; number++)
        {
            foreach (var box in pages[number].Bars)
            {
                if (box.Bar > written || (found is not null && found.Box.Bar > box.Bar))
                {
                    continue;
                }
                found = new Mark(number, box);
            }
        }
        return found;
    }

    /// <summary>The written bar whose rectangle holds the point, in page pixels
    /// (<c>marker.bar_at_point</c>).</summary>
    public static int? BarAt(double x, double y, SheetPage page) =>
        page.Bars.FirstOrDefault(box => box.X <= x && x <= box.X + box.Width && box.Y <= y && y <= box.Y + box.Height)?.Bar;
}
