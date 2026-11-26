using System.Globalization;
using System.Net;
using System.Text;
using System.Text.Json;

namespace Stickler.Core;

/// <summary>The window's Ctrl keys that also work while the sheet has the focus
/// (<see cref="SheetHtml.AcceleratorScript"/>): Ctrl+Plus, Ctrl+Minus, Ctrl+0, Ctrl+O, Ctrl+W and
/// Ctrl+Shift+C.</summary>
public enum SheetAccelerator
{
    ZoomIn,
    ZoomOut,
    ActualSize,
    Open,
    Close,
    Corrections,
}

/// <summary>A colour as bytes.</summary>
public readonly record struct Rgb(byte Red, byte Green, byte Blue);

/// <summary>What the marker shows: the view sends <see cref="SheetHtml.MarkScript"/> again only
/// when this changed or the pages were replaced.</summary>
public sealed record Marking(Marker.Mark? Mark, Rgb Accent, bool Dark, double Room)
{
    /// <summary>The script that draws it.</summary>
    public string Script => SheetHtml.MarkScript(Mark, Accent, Dark, Room);
}

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
            #marker { position: absolute; border-radius: 5px; pointer-events: none; }
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

    /// <summary>Draws the playback marker over a page's bar or takes it away (no mark), and scrolls
    /// it into view when it is above the window or below <c>innerHeight - room</c> (the Mac's
    /// <c>markScript</c>). One self-contained expression for <c>ExecuteScriptAsync</c>: the values
    /// are literals in it, numbers in the invariant culture, the colour as a JSON string. The
    /// answer is <c>true</c> when a marker is shown.</summary>
    public static string MarkScript(Marker.Mark? mark, Rgb accent, bool dark, double room)
    {
        var alpha = dark ? "0.32" : "0.2";
        var colour = mark is null ? "" : $"rgba({accent.Red}, {accent.Green}, {accent.Blue}, {alpha})";
        var box = mark?.Box;
        return $$"""
            (() => {
            const page = {{(mark?.Page ?? -1).ToString(CultureInfo.InvariantCulture)}};
            const x = {{Number(box?.X ?? 0)}}, y = {{Number(box?.Y ?? 0)}};
            const width = {{Number(box?.Width ?? 0)}}, height = {{Number(box?.Height ?? 0)}};
            const colour = {{Content.Literal(colour)}};
            const room = {{Number(mark is null ? 0 : room)}};
            let mark = document.getElementById("marker");
            const host = page < 0 ? null : document.querySelectorAll(".page")[page];
            if (!host) { if (mark) { mark.remove(); } return false; }
            if (!mark) { mark = document.createElement("div"); mark.id = "marker"; }
            if (mark.parentNode !== host) { host.appendChild(mark); }
            mark.style.left = x + "px"; mark.style.top = y + "px";
            mark.style.width = width + "px"; mark.style.height = height + "px";
            mark.style.background = colour;
            const seen = mark.getBoundingClientRect();
            if (seen.top < 0 || seen.bottom > window.innerHeight - room) {
              window.scrollTo(0, window.scrollY + seen.top - (window.innerHeight - room) / 3);
            }
            return true;
            })()
            """;
    }

    /// <summary>The page's click listener, added to every document (the app's own script; the
    /// page's own stay off). A plain primary click on a page posts <c>bar:page:x:y</c> (the
    /// page's index and the point in page pixels, undoing a zoom's scale), as the Mac's
    /// <c>hitScript</c> finds it; <see cref="BarOfClick"/> reads it.</summary>
    public const string ClickScript = """
        document.addEventListener("click", event => {
          if (event.button !== 0 || event.ctrlKey || event.shiftKey || event.altKey || event.metaKey) { return; }
          const pages = document.querySelectorAll(".page");
          for (let k = 0; k < pages.length; k++) {
            const r = pages[k].getBoundingClientRect();
            if (event.clientX >= r.left && event.clientX <= r.right && event.clientY >= r.top && event.clientY <= r.bottom) {
              const scale = r.width / Math.max(1, pages[k].offsetWidth);
              window.chrome.webview.postMessage("bar:" + k + ":" + ((event.clientX - r.left) / scale) + ":" + ((event.clientY - r.top) / scale));
              return;
            }
          }
        });
        """;

    /// <summary>The written bar a <see cref="ClickScript"/> message is on, in the shown pages;
    /// <c>null</c> for a miss, any other message, a malformed one or a page no longer shown.</summary>
    public static int? BarOfClick(string message, IReadOnlyList<SheetPage> pages)
    {
        var parts = message.Split(':');
        if (parts.Length != 4 || parts[0] != "bar"
            || !int.TryParse(parts[1], NumberStyles.None, CultureInfo.InvariantCulture, out var page)
            || page >= pages.Count
            || !double.TryParse(parts[2], NumberStyles.Float, CultureInfo.InvariantCulture, out var x)
            || !double.TryParse(parts[3], NumberStyles.Float, CultureInfo.InvariantCulture, out var y)
            || !double.IsFinite(x) || !double.IsFinite(y))
        {
            return null;
        }
        return Marker.BarAt(x, y, pages[page]);
    }

    /// <summary>The page's key listener, added to every document beside <see cref="ClickScript"/>.
    /// With the web view focused (after a click on a bar) the window's accelerators do not see
    /// plain keys, so Space (not as an auto-repeat), Left, Right and Home, pressed without
    /// Ctrl, Alt, Shift or Meta, are posted as <c>key:space</c>, <c>key:left</c>,
    /// <c>key:right</c> and <c>key:home</c> and kept from the page; every other key (Page
    /// Up/Down, Up/Down) is left to it. <see cref="KeyOfMessage"/> reads the message.</summary>
    public const string KeyScript = """
        document.addEventListener("keydown", event => {
          if (event.ctrlKey || event.altKey || event.shiftKey || event.metaKey) { return; }
          const keys = { " ": "space", "ArrowLeft": "left", "ArrowRight": "right", "Home": "home" };
          const name = Object.prototype.hasOwnProperty.call(keys, event.key) ? keys[event.key] : null;
          if (name === null || (name === "space" && event.repeat)) { return; }
          event.preventDefault();
          window.chrome.webview.postMessage("key:" + name);
        }, true);
        """;

    /// <summary>The window's Ctrl keys from inside the sheet: while the page has the focus the
    /// window's accelerators never see them (seen in the VM, 2026-11-26: Ctrl+Plus did nothing
    /// after a click into the sheet). Each is posted as <c>accel:name</c> and kept from the
    /// browser; <see cref="AcceleratorOfMessage"/> reads it. Every other key is left alone.</summary>
    public const string AcceleratorScript = """
        document.addEventListener("keydown", event => {
          if (!event.ctrlKey || event.altKey || event.metaKey) { return; }
          const plain = { "+": "zoom_in", "=": "zoom_in", "-": "zoom_out", "0": "actual_size", "o": "open", "w": "close" };
          const shifted = { "c": "corrections" };
          const keys = event.shiftKey && event.key !== "+" ? shifted : plain;
          const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
          const name = Object.prototype.hasOwnProperty.call(keys, key) ? keys[key] : null;
          if (name === null) { return; }
          event.preventDefault();
          if (!event.repeat || name.startsWith("zoom")) { window.chrome.webview.postMessage("accel:" + name); }
        }, true);
        """;

    /// <summary>What an <see cref="AcceleratorScript"/> message asks for; <c>null</c> for any
    /// other message.</summary>
    public static SheetAccelerator? AcceleratorOfMessage(string message) => message switch
    {
        "accel:zoom_in" => SheetAccelerator.ZoomIn,
        "accel:zoom_out" => SheetAccelerator.ZoomOut,
        "accel:actual_size" => SheetAccelerator.ActualSize,
        "accel:open" => SheetAccelerator.Open,
        "accel:close" => SheetAccelerator.Close,
        "accel:corrections" => SheetAccelerator.Corrections,
        _ => null,
    };

    /// <summary>The key a <see cref="KeyScript"/> message names; <c>null</c> for any other message.</summary>
    public static PlaybackKey? KeyOfMessage(string message) => message switch
    {
        "key:space" => PlaybackKey.Space,
        "key:left" => PlaybackKey.Left,
        "key:right" => PlaybackKey.Right,
        "key:home" => PlaybackKey.Home,
        _ => null,
    };

    /// <summary>A number as a JavaScript literal, whatever the culture (0 for NaN and infinities).</summary>
    private static string Number(double value) =>
        double.IsFinite(value) ? value.ToString("R", CultureInfo.InvariantCulture) : "0";

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
        internal static string Literal(string text)
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
