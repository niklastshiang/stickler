using System.Globalization;

namespace Stickler.Core.Tests;

/// <summary>The playback marker and a click on a bar (SPEC.md, <c>win-playback</c>, scope 5; the
/// Mac's <c>MarkerTests</c>).</summary>
[TestClass]
public sealed class MarkerTests
{
    private static readonly Rgb Accent = new(0, 96, 223);
    private static readonly BarBox Box = new(2, 10, 20, 30, 40);

    private static SheetPage Page(string svg = "<svg/>") => new(svg, 800, 100, [Box]);

    [TestMethod]
    public void TheMarkerIsDrawnOverThePaperNotInvertedWithIt()
    {
        var dark = SheetHtml.Sheets([Page("<svg id=\"one\"/>")], dark: true);
        Assert.Contains(".paper { box-shadow: 0 1px 3px rgba(0,0,6,.18); background: #e4e4e6;", dark.Style);
        Assert.Contains(".page { position: relative;", dark.Style);
        Assert.Contains("#marker { position: absolute;", dark.Style);
        Assert.Contains("pointer-events: none", dark.Style);
        var document = dark.Document;
        Assert.Contains("<div class=\"paper\"><svg", document);
        Assert.DoesNotContain("<script", document);
        // the marker's rule is not one of the paper's, which carries the inversion
        var rule = dark.Style.Split('\n').Single(line => line.StartsWith("#marker", StringComparison.Ordinal));
        Assert.DoesNotContain("invert", rule);
        Assert.IsGreaterThan(dark.Style.IndexOf(".paper", StringComparison.Ordinal), dark.Style.IndexOf("#marker", StringComparison.Ordinal));
        Assert.IsLessThan(document.IndexOf("</div></div>", StringComparison.Ordinal), document.IndexOf("class=\"paper\"", StringComparison.Ordinal));
    }

    [TestMethod]
    public void ThePolicyStillForbidsPageScripts()
    {
        Assert.AreEqual("default-src 'none'; style-src 'unsafe-inline'; font-src data:; img-src data:", SheetHtml.Policy);
        Assert.DoesNotContain("script-src", SheetHtml.Policy);
        Assert.DoesNotContain("<script", SheetHtml.Sheets([Page()], dark: false).Document);
    }

    [TestMethod]
    public void TheMarkerIsTheBarsRectangleInTheAccentColour()
    {
        var light = SheetHtml.MarkScript(new Marker.Mark(1, Box), Accent, dark: false, room: 84);
        Assert.Contains("const page = 1;", light);
        Assert.Contains("const x = 10, y = 20;", light);
        Assert.Contains("const width = 30, height = 40;", light);
        Assert.Contains("const colour = \"rgba(0, 96, 223, 0.2)\";", light);
        Assert.Contains("const room = 84;", light);
        var dark = new Marking(new Marker.Mark(1, Box), Accent, Dark: true, Room: 0).Script;
        Assert.Contains("\"rgba(0, 96, 223, 0.32)\"", dark);
        var none = SheetHtml.MarkScript(null, Accent, dark: false, room: 84);
        Assert.Contains("const page = -1;", none, "no bar sounds: the marker goes");
        Assert.Contains("const room = 0;", none);
        Assert.Contains("mark.remove()", none);
    }

    [TestMethod]
    public void TheMarkerKeepsItsScrollRule()
    {
        var script = SheetHtml.MarkScript(new Marker.Mark(0, Box), Accent, dark: false, room: 0);
        Assert.Contains("seen.top < 0 || seen.bottom > window.innerHeight - room", script);
        Assert.Contains("window.scrollTo(0, window.scrollY + seen.top - (window.innerHeight - room) / 3)", script);
        Assert.Contains("return true;", script);
        Assert.StartsWith("(() => {", script);
        Assert.EndsWith("})()", script);
    }

    [TestMethod]
    public void NumbersAreWrittenTheSameInEveryCulture()
    {
        var before = CultureInfo.CurrentCulture;
        try
        {
            CultureInfo.CurrentCulture = new CultureInfo("de-DE");
            var script = SheetHtml.MarkScript(new Marker.Mark(0, new BarBox(1, 10.5, 20.25, 30.125, 40)), Accent, dark: true, room: 84.5);
            Assert.Contains("const x = 10.5, y = 20.25;", script);
            Assert.Contains("const width = 30.125, height = 40;", script);
            Assert.Contains("rgba(0, 96, 223, 0.32)", script);
            Assert.Contains("const room = 84.5;", script);
            Assert.DoesNotContain("10,5", script);
        }
        finally
        {
            CultureInfo.CurrentCulture = before;
        }
    }

    [TestMethod]
    public void NoValueCanBreakOutOfTheScript()
    {
        var script = SheetHtml.MarkScript(
            new Marker.Mark(0, new BarBox(1, double.NaN, double.PositiveInfinity, double.NegativeInfinity, 1e300)), Accent, dark: false, room: double.NaN);
        Assert.Contains("const x = 0, y = 0;", script);
        Assert.Contains("const width = 0, height = 1E+300;", script);
        Assert.Contains("const room = 0;", script);
        // no text from outside reaches the script: numbers and bytes only, and the colour as a JSON string
        Assert.DoesNotContain("NaN", script);
        Assert.DoesNotContain("Infinity", script);
    }

    [TestMethod]
    public void AClickFindsTheBarUnderItFromThePagesMessage()
    {
        SheetPage[] pages = [Page()];
        Assert.AreEqual(2, SheetHtml.BarOfClick("bar:0:25:30", pages));
        Assert.AreEqual(2, SheetHtml.BarOfClick("bar:0:25.5:30.25", pages));
        Assert.AreEqual(2, SheetHtml.BarOfClick("bar:0:2.5e1:3E1", pages)); // as JavaScript writes numbers
        Assert.IsNull(SheetHtml.BarOfClick("bar:0:5:5", pages), "on the page, between the bars");
    }

    [TestMethod]
    public void AMessageThatIsNotAClickOnABarIsNothing()
    {
        SheetPage[] pages = [Page()];
        string[] messages =
        [
            "", "zoom_in", "bar", "bar:0:25", "bar:0:25:30:1", "bar:3:25:30", "bar:1:25:30", "bar:-1:25:30", "bar:+0:25:30",
            "bar:0.5:25:30", "bar: 0:25:30", "bar::25:30", "bar:0::30", "bar:0:25:", "bar:0:x:30", "bar:0:25:y",
            "bar:0:NaN:30", "bar:0:25:Infinity", "bar:0:-Infinity:30", "bar:0:1e999:30", "BAR:0:25:30", "bar:99999999999:25:30",
            "bar:0:25,5:30",
        ];
        foreach (var message in messages)
        {
            Assert.IsNull(SheetHtml.BarOfClick(message, pages), message);
        }
        Assert.IsNull(SheetHtml.BarOfClick("bar:0:25:30", []), "no pages shown");
    }

    [TestMethod]
    public void TheClickScriptIgnoresModifiedAndSecondaryClicksAndMisses()
    {
        var script = SheetHtml.ClickScript;
        Assert.Contains("event.button !== 0", script);
        foreach (var held in new[] { "ctrlKey", "shiftKey", "altKey", "metaKey" })
        {
            Assert.Contains($"event.{held}", script);
        }
        Assert.Contains("window.chrome.webview.postMessage(\"bar:\"", script);
        Assert.Contains("Math.max(1, pages[k].offsetWidth)", script);
    }

    [TestMethod]
    public void EachKeyMessageNamesItsKeyAndNothingElseDoes()
    {
        Assert.AreEqual(PlaybackKey.Space, SheetHtml.KeyOfMessage("key:space"));
        Assert.AreEqual(PlaybackKey.Left, SheetHtml.KeyOfMessage("key:left"));
        Assert.AreEqual(PlaybackKey.Right, SheetHtml.KeyOfMessage("key:right"));
        Assert.AreEqual(PlaybackKey.Home, SheetHtml.KeyOfMessage("key:home"));
        foreach (var message in new[] { "bar:0:1:2", "zoom_in", "key:", "key:Space", "key:up", "key:space ", "KEY:space", "" })
        {
            Assert.IsNull(SheetHtml.KeyOfMessage(message), message);
        }
    }

    [TestMethod]
    public void AnAcceleratorMessageNamesWhatTheWindowDoes()
    {
        Assert.AreEqual(SheetAccelerator.ZoomIn, SheetHtml.AcceleratorOfMessage("accel:zoom_in"));
        Assert.AreEqual(SheetAccelerator.ZoomOut, SheetHtml.AcceleratorOfMessage("accel:zoom_out"));
        Assert.AreEqual(SheetAccelerator.ActualSize, SheetHtml.AcceleratorOfMessage("accel:actual_size"));
        Assert.AreEqual(SheetAccelerator.Open, SheetHtml.AcceleratorOfMessage("accel:open"));
        Assert.AreEqual(SheetAccelerator.Close, SheetHtml.AcceleratorOfMessage("accel:close"));
        Assert.AreEqual(SheetAccelerator.Corrections, SheetHtml.AcceleratorOfMessage("accel:corrections"));
        foreach (var message in new[] { "", "accel:", "accel:Open", "accel:zoom", "zoom_in", "key:space", "bar:0:1:2", "accel:open " })
        {
            Assert.IsNull(SheetHtml.AcceleratorOfMessage(message), message);
        }
    }

    [TestMethod]
    public void TheAcceleratorScriptTakesOnlyTheWindowsCtrlKeys()
    {
        var script = SheetHtml.AcceleratorScript;
        Assert.Contains("addEventListener(\"keydown\"", script);
        Assert.Contains("}, true);", script, "capture phase");
        Assert.Contains("if (!event.ctrlKey || event.altKey || event.metaKey) { return; }", script, "Ctrl alone or with Shift, never AltGr");
        Assert.Contains("event.preventDefault()", script);
        Assert.Contains("window.chrome.webview.postMessage(\"accel:\" + name)", script);
        foreach (var key in new[] { "\"+\": \"zoom_in\"", "\"=\": \"zoom_in\"", "\"-\": \"zoom_out\"", "\"0\": \"actual_size\"", "\"o\": \"open\"", "\"w\": \"close\"", "\"c\": \"corrections\"" })
        {
            Assert.Contains(key, script);
        }
        // every name the script can post is one the app reads
        foreach (System.Text.RegularExpressions.Match name in System.Text.RegularExpressions.Regex.Matches(script, "\": \"([a-z_]+)\""))
        {
            Assert.IsNotNull(SheetHtml.AcceleratorOfMessage("accel:" + name.Groups[1].Value), name.Groups[1].Value);
        }
        Assert.DoesNotContain("\"c\": \"copy\"", script);
    }

    [TestMethod]
    public void TheKeyScriptTakesOnlyThoseFourPlainKeys()
    {
        var script = SheetHtml.KeyScript;
        Assert.Contains("addEventListener(\"keydown\"", script);
        Assert.Contains("}, true);", script, "capture phase");
        foreach (var held in new[] { "ctrlKey", "altKey", "shiftKey", "metaKey" })
        {
            Assert.Contains($"event.{held}", script);
        }
        Assert.Contains("event.repeat", script);
        Assert.Contains("event.preventDefault()", script);
        Assert.Contains("window.chrome.webview.postMessage(\"key:\" + name)", script);
        foreach (var key in new[] { "\" \": \"space\"", "\"ArrowLeft\": \"left\"", "\"ArrowRight\": \"right\"", "\"Home\": \"home\"" })
        {
            Assert.Contains(key, script);
        }
        Assert.DoesNotContain("PageUp", script);
        Assert.DoesNotContain("ArrowUp", script);
        Assert.DoesNotContain("ArrowDown", script);
    }

    [TestMethod]
    public void MarkingsAreEqualByValue()
    {
        var mark = new Marker.Mark(1, Box);
        var first = new Marking(mark, Accent, false, 0);
        Assert.AreEqual(first, new Marking(new Marker.Mark(1, new BarBox(2, 10, 20, 30, 40)), new Rgb(0, 96, 223), false, 0));
        Assert.AreNotEqual(first, first with { Dark = true });
        Assert.AreNotEqual(first, first with { Room = 84 });
        Assert.AreNotEqual(first, first with { Accent = new Rgb(1, 96, 223) });
        Assert.AreNotEqual(first, first with { Mark = new Marker.Mark(0, Box) });
        Assert.AreNotEqual(first, first with { Mark = null });
        Assert.AreEqual(first.Script, new Marking(mark, Accent, false, 0).Script);
    }
}
