using System.Globalization;
using System.Net;
using System.Text;
using System.Text.Json;

namespace Stickler.Core;

/// <summary>The page the sheet's WebView2 shows (SPEC.md, module <c>win-sheet</c>, scope 1;
/// design screen W6), as the Mac's <c>SheetHTML</c>: the core's pages one under the other on the
/// grey desk, each on white paper with the canvas's shadow; in dark mode the paper is inverted
/// (light notes on a dark page). Plain HTML and CSS: the page runs no script of its own, and
/// its policy fetches nothing.</summary>
public static class SheetHtml
{
    /// <summary>The desk around and between the pages, in effective pixels (the GTK and Mac sheets' gutter).</summary>
    public const double Gutter = 12;

    /// <summary>The address the window serves the page under (from memory, never from disk).</summary>
    public const string Address = "https://sheet.stickler.invalid/";

    /// <summary>Nothing is fetched for the page: the core's SVG brings its font and styles with it.</summary>
    public const string Policy = "default-src 'none'; style-src 'unsafe-inline'; font-src data:; img-src data:";

    /// <summary>The width to ask the core for: the view's, less the desk on both sides. Nothing
    /// while the view is too narrow to show a page.</summary>
    public static double? PagesWidth(double view)
    {
        var width = view - (2 * Gutter);
        return width >= 1 ? width : null;
    }

    /// <summary>The desk's grey (W6: <c>#e8e8e8</c>, dark <c>#161616</c>) as CSS.</summary>
    public static string Desk(bool dark) => dark ? "#161616" : "#e8e8e8";

    /// <summary>What Narrator reads for the sheet, which is one picture to it: the song's title
    /// and the page count ("Sheet music of Eye of the Tiger, 3 pages").</summary>
    public static string Label(string title, int pages, Strings strings) =>
        strings.Text("Sheet music of {title}", ("title", title)) + ", "
        + strings.Plural("{count} page", pages, ("count", pages.ToString(CultureInfo.CurrentCulture)));

    /// <summary>The page's styles and sheets for <paramref name="pages"/> in the window's theme.</summary>
    public static Content Sheets(IReadOnlyList<SheetPage> pages, bool dark)
    {
        // the canvas inverts a light grey paper, so the dark page is not pure black
        var paper = dark ? "background: #e4e4e6; filter: invert(1) hue-rotate(180deg);" : "background: #ffffff;";
        var sheets = new StringBuilder();
        foreach (var page in pages)
        {
            // the paper inside the page, so the playback marker over it is not inverted with it
            sheets.Append(CultureInfo.InvariantCulture, $"<div class=\"page\" style=\"width: {Px(page.Width)}px;\">")
                .Append("<div class=\"paper\">").Append(page.Svg).Append("</div></div>\n");
        }
        var style = $$"""
            html { background: {{Desk(dark)}}; overflow-x: hidden; }
            body { margin: 0; padding: {{Px(Gutter)}}px; cursor: default; user-select: none; }
            .page { position: relative; margin: 0 auto {{Px(Gutter)}}px; }
            .paper { box-shadow: 0 1px 3px rgba(0,0,6,.18); {{paper}} }
            .page:last-child { margin-bottom: 0; }
            .page svg { display: block; }
            """;
        return new Content(style, sheets.ToString());
    }

    /// <summary>The A4 document the PDF is printed from: one page of the core's A4 pages to each
    /// printed page, the Leipzig font (<paramref name="font"/>, the TTF's bytes) as a data URL,
    /// the title as the document's.</summary>
    public static string A4Document(A4Pages pages, ReadOnlySpan<byte> font)
    {
        var sheets = new StringBuilder();
        foreach (var page in pages.Sheets)
        {
            sheets.Append("<div class=\"a4\">").Append(page.Svg).Append("</div>\n");
        }
        // Verovio embeds a subset of Leipzig in each SVG; the whole font keeps the tempo mark
        // right if that ever changes (as the Mac's PDF)
        var face = $"@font-face {{ font-family: Leipzig; src: url(data:font/ttf;base64,{Convert.ToBase64String(font)}); }}";
        return $$"""
            <!doctype html><html><head><meta charset="utf-8">
            <meta http-equiv="Content-Security-Policy" content="{{Policy}}">
            <title>{{WebUtility.HtmlEncode(pages.Title)}}</title><style>
            {{face}}
            @page { size: A4; margin: 0; }
            html, body { margin: 0; padding: 0; background: #ffffff; }
            .a4 { width: 210mm; height: 297mm; overflow: hidden; break-after: page; }
            .a4:last-child { break-after: auto; }
            .a4 svg { display: block; width: 100%; height: 100%; }
            </style></head><body>
            {{sheets}}</body></html>
            """;
    }

    /// <summary>Effective pixels as CSS writes them, whatever the reader's culture.</summary>
    private static string Px(double value) => value.ToString("0.##", CultureInfo.InvariantCulture);

    /// <summary>What the sheet's view shows: its styles and sheets. The document is loaded once;
    /// pages laid out again replace both in it (<see cref="Replace"/>), so the sheet is never
    /// blank in between and keeps its scroll position.</summary>
    public sealed record Content(string Style, string Sheets)
    {
        /// <summary>The whole document, for the first load.</summary>
        public string Document => $"""
            <!doctype html><html><head><meta charset="utf-8">
            <meta http-equiv="Content-Security-Policy" content="{Policy}"><style id="style">
            {Style}
            </style></head><body aria-hidden="true">
            {Sheets}</body></html>
            """;

        /// <summary>The app's own script that puts this content into the loaded document
        /// (WebView2 runs it although the page's own scripts are off).</summary>
        public string Replace =>
            $"document.getElementById('style').textContent = {Literal(Style)};"
            + $" document.body.innerHTML = {Literal(Sheets)}; true";

        /// <summary>A string as a JavaScript literal (JSON's, with <c>&lt;</c> and the like escaped).</summary>
        private static string Literal(string text)
        {
            using var buffer = new MemoryStream();
            using (var writer = new Utf8JsonWriter(buffer))
            {
                writer.WriteStringValue(text);
            }
            return Encoding.UTF8.GetString(buffer.ToArray());
        }
    }
}
