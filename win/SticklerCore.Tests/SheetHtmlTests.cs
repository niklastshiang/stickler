using System.Globalization;

namespace Stickler.Core.Tests;

[TestClass]
public sealed class SheetHtmlTests
{
    private static readonly string Tables = Path.Combine(Repo.Root, "win", "Stickler", "Strings");

    private static SheetPage Page(string svg, double width = 800.5) => new(svg, width, 300, []);

    [TestMethod]
    public void ThePagesAreAsWideAsTheViewLessTheDesk()
    {
        Assert.AreEqual(800.0, SheetHtml.PagesWidth(824));
        Assert.AreEqual(1.0, SheetHtml.PagesWidth(25));
        Assert.IsNull(SheetHtml.PagesWidth(24.5));
    }

    [TestMethod]
    public void NarratorHearsTheTitleAndThePageCountInTheReadersLanguage()
    {
        var english = Strings.Load(Tables, ["en-US"]);
        Assert.AreEqual("Sheet music of Eye of the Tiger, 3 pages", SheetHtml.Label("Eye of the Tiger", 3, english));
        Assert.AreEqual("Sheet music of Groove, 1 page", SheetHtml.Label("Groove", 1, english));
        var german = Strings.Load(Tables, ["de-DE"]);
        Assert.AreEqual("Noten von Eye of the Tiger, 3 Seiten", SheetHtml.Label("Eye of the Tiger", 3, german));
    }

    [TestMethod]
    public void ThePagesComeInOrderOnTheDeskWithoutAScript()
    {
        var content = SheetHtml.Sheets([Page("<svg id=\"one\"/>"), Page("<svg id=\"two\"/>")], dark: false);
        Assert.IsLessThan(content.Sheets.IndexOf("two", StringComparison.Ordinal), content.Sheets.IndexOf("one", StringComparison.Ordinal));
        Assert.Contains("#e8e8e8", content.Style);
        Assert.Contains("box-shadow: 0 1px 3px", content.Style);
        Assert.DoesNotContain("invert", content.Style);
        var document = content.Document;
        Assert.Contains(SheetHtml.Policy, document);
        Assert.DoesNotContain("<script", document);
        Assert.Contains("<style id=\"style\">", document);
        Assert.Contains("aria-hidden=\"true\"", document);
    }

    [TestMethod]
    public void InDarkModeThePaperIsInvertedOnTheDarkDesk()
    {
        var content = SheetHtml.Sheets([Page("<svg/>")], dark: true);
        Assert.Contains("#161616", content.Style);
        Assert.Contains("filter: invert(1) hue-rotate(180deg)", content.Style);
        Assert.AreEqual("#161616", SheetHtml.Desk(dark: true));
    }

    [TestMethod]
    public void WidthsAreWrittenTheSameInEveryCulture()
    {
        var before = CultureInfo.CurrentCulture;
        try
        {
            CultureInfo.CurrentCulture = new CultureInfo("de-DE");
            var content = SheetHtml.Sheets([Page("<svg/>", width: 800.5)], dark: false);
            Assert.Contains("width: 800.5px;", content.Sheets);
            Assert.Contains("padding: 12px;", content.Style);
        }
        finally
        {
            CultureInfo.CurrentCulture = before;
        }
    }

    [TestMethod]
    public void NewPagesReplaceTheLoadedOnesThroughTheAppsOwnScript()
    {
        var content = SheetHtml.Sheets([Page("<svg><text>a \"b\" </script></text></svg>")], dark: false);
        var script = content.Replace;
        Assert.StartsWith("document.getElementById('style').textContent = \"", script);
        Assert.Contains("document.body.innerHTML = \"", script);
        // a string literal that cannot end the script or the string early
        Assert.DoesNotContain("</script>", script);
        Assert.Contains("\\u0022b\\u0022", script);
        Assert.EndsWith("; true", script);
    }

    [TestMethod]
    public void TheA4DocumentHasOnePagePerSheetTheFontAndTheTitle()
    {
        var pages = new A4Pages("Rock <&> Roll", [Page("<svg id=\"p1\"/>", 1050), Page("<svg id=\"p2\"/>", 1050)]);
        var document = SheetHtml.A4Document(pages, [0x00, 0x01, 0x02]);
        Assert.Contains("<title>Rock &lt;&amp;&gt; Roll</title>", document);
        Assert.Contains("@page { size: A4; margin: 0; }", document);
        Assert.Contains("src: url(data:font/ttf;base64,AAEC);", document);
        Assert.AreEqual(2, document.Split("<div class=\"a4\">").Length - 1);
        Assert.IsLessThan(document.IndexOf("p2", StringComparison.Ordinal), document.IndexOf("p1", StringComparison.Ordinal));
        Assert.DoesNotContain("<script", document);
    }
}
