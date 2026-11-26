using System.ComponentModel;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.Web.WebView2.Core;
using Stickler.Core;

namespace Stickler;

/// <summary>The sheet music in WebView2 (SPEC.md, module <c>win-sheet</c>, scopes 2–5): the
/// core's pages as <see cref="SheetModel"/> holds them, served from memory under
/// <see cref="SheetHtml.Address"/>; its width goes back to the model. The page runs no script
/// of its own; the app's own scripts put new pages into the loaded document and turn Ctrl+wheel
/// (a touchpad's pinch arrives as one) into the core's zoom steps; for playback (module
/// <c>win-playback</c>, scope 5) they draw the marker and report a click on a bar and the
/// playback's keys. A pure view: checked by
/// screenshots and by hand, not counted for coverage.</summary>
public sealed partial class SheetView : UserControl
{
    /// <summary>Ctrl+wheel and a pinch as zoom steps: one step per notch (100 pixels of wheel),
    /// a pinch's many small events added up first. Sent to the app as a web message.</summary>
    private const string WheelScript = """
        (() => {
          let sum = 0;
          window.addEventListener('wheel', e => {
            if (!e.ctrlKey) { return; }
            e.preventDefault();
            sum += e.deltaY;
            if (Math.abs(sum) >= 100) {
              window.chrome.webview.postMessage(sum < 0 ? 'zoom_in' : 'zoom_out');
              sum = 0;
            }
          }, { passive: false });
        })();
        """;

    private const string PrintAddress = SheetHtml.Address + "print";

    private SheetModel? sheet;
    private PlaybackModel? playback;
    private Action<PlaybackKey> pressed = _ => { };
    private Marking? marking; // the marker as the page shows it; null after new pages
    private Strings strings = Strings.English;
    private string title = "";
    private Task<CoreWebView2Environment>? environment;
    private byte[] document = [];
    private byte[] printDocument = [];
    private bool loaded; // the document is there: new pages replace its content
    private bool navigating;
    private SheetHtml.Content? shown;
    private ulong sheetNavigation; // ours: completions of a cancelled one (a dropped file) are not
    private TaskCompletionSource<bool>? printed;
    private ulong printNavigation;
    private Task<bool>? printing; // one PDF at a time, also after one ran out of time
    private Action<string> failed = _ => { };

    public SheetView()
    {
        InitializeComponent();
        SizeChanged += (_, _) => ReportWidth();
        ActualThemeChanged += (_, _) =>
        {
            Show();
            Mark();
        };
    }

    /// <summary>Where WebView2 keeps its data: under Stickler's folder, not next to the .exe
    /// (an installed app's folder is the program's), removed with Stickler's data.</summary>
    public static string DataFolder =>
        Path.Combine(System.Environment.GetFolderPath(System.Environment.SpecialFolder.LocalApplicationData), "Stickler", "WebView2");

    /// <summary>Starts the view on <paramref name="model"/>'s pages; <paramref name="fail"/>
    /// tells the reader why WebView2 could not start (its own words), instead of a grey desk.</summary>
    public void Attach(SheetModel model, PlaybackModel playing, Strings words, Action<string> fail, Action<PlaybackKey> key)
    {
        sheet = model;
        playback = playing;
        strings = words;
        failed = fail;
        pressed = key;
        sheet.PropertyChanged += OnSheetChanged;
        playback.PropertyChanged += OnPlaybackChanged;
        _ = StartOrSayWhyAsync();
    }

    private async Task StartOrSayWhyAsync()
    {
        try
        {
            await StartAsync();
        }
        catch (Exception error) when (error is System.Runtime.InteropServices.COMException or InvalidOperationException or ArgumentException or UnauthorizedAccessException or IOException)
        {
            failed(error.Message);
        }
    }

    /// <summary>The song's title, for Narrator's name of the sheet.</summary>
    public string SongTitle
    {
        get => title;
        set
        {
            title = value;
            Label();
        }
    }

    private Task<CoreWebView2Environment> Environment() =>
        environment ??= CoreWebView2Environment.CreateWithOptionsAsync(
            "", DataFolder, new CoreWebView2EnvironmentOptions { ScrollBarStyle = CoreWebView2ScrollbarStyle.FluentOverlay }).AsTask();

    private async Task StartAsync()
    {
        await Web.EnsureCoreWebView2Async(await Environment());
        var core = Web.CoreWebView2;
        Lock(core.Settings);
        // The app's own listeners (the wheel, a click on a bar, the playback's keys) need scripts
        // on: with them off the listeners are registered but never called (seen in the VM,
        // 2026-11-26). The page's content still brings none: its policy has no script-src.
        core.Settings.IsScriptEnabled = true;
        core.Settings.IsWebMessageEnabled = true; // the listeners' messages
        await core.AddScriptToExecuteOnDocumentCreatedAsync(WheelScript);
        await core.AddScriptToExecuteOnDocumentCreatedAsync(SheetHtml.ClickScript);
        await core.AddScriptToExecuteOnDocumentCreatedAsync(SheetHtml.KeyScript);
        core.AddWebResourceRequestedFilter(SheetHtml.Address + "*", CoreWebView2WebResourceContext.All);
        core.WebResourceRequested += (_, e) => Serve(core, e, document);
        core.NavigationStarting += (_, e) =>
        {
            e.Cancel = e.Uri != SheetHtml.Address;
            if (!e.Cancel)
            {
                sheetNavigation = e.NavigationId;
            }
        };
        core.NewWindowRequested += (_, e) => e.Handled = true;
        core.NavigationCompleted += (_, e) =>
        {
            if (e.NavigationId != sheetNavigation)
            {
                return; // one we refused: the document shown is still ours
            }
            navigating = false;
            loaded = e.IsSuccess;
            if (!e.IsSuccess)
            {
                shown = null; // loaded again with the next pages
            }
            Show(); // pages that came while it loaded
            marking = null;
            Mark();
        };
        core.WebMessageReceived += (_, e) => Step(e.TryGetWebMessageAsString());
        ReportWidth();
        Show();
    }

    /// <summary>What the page may do: nothing but show the pages.</summary>
    private static void Lock(CoreWebView2Settings settings)
    {
        settings.IsScriptEnabled = false; // the sheet's view turns it on for the app's own listeners
        settings.IsWebMessageEnabled = false;
        settings.AreDefaultContextMenusEnabled = false;
        settings.AreDevToolsEnabled = false;
        settings.IsStatusBarEnabled = false;
        settings.AreBrowserAcceleratorKeysEnabled = false;
        settings.IsZoomControlEnabled = false; // the core engraves at a new size instead
        settings.IsPinchZoomEnabled = false;
        settings.IsSwipeNavigationEnabled = false;
        settings.IsGeneralAutofillEnabled = false;
        settings.IsPasswordAutosaveEnabled = false;
        settings.AreHostObjectsAllowed = false;
    }

    private static void Serve(CoreWebView2 core, CoreWebView2WebResourceRequestedEventArgs e, byte[] page)
    {
        // the page from memory, without waiting on the window's thread for a write
        var stream = new MemoryStream(page, writable: false).AsRandomAccessStream();
        e.Response = core.Environment.CreateWebResourceResponse(stream, 200, "OK", "Content-Type: text/html; charset=utf-8");
    }

    private void OnSheetChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(SheetModel.Pages))
        {
            Show();
            Label();
        }
    }

    private void OnPlaybackChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(PlaybackModel.Marked))
        {
            Mark();
        }
    }

    /// <summary>The sounding bar marked in the accent colour (W10), sent to the page only when
    /// it changed or the pages are new. The bar is outside the page, so nothing of the view is
    /// covered: no room is kept free.</summary>
    private void Mark()
    {
        if (sheet is null || playback is null || Web.CoreWebView2 is not { } core || !loaded || navigating)
        {
            return;
        }
        var dark = ActualTheme == ElementTheme.Dark;
        var accent = (Windows.UI.Color)Application.Current.Resources[dark ? "SystemAccentColorLight2" : "SystemAccentColorDark1"];
        var mark = playback.Marked is { } written ? Marker.Locate(written, sheet.Pages) : null;
        var next = new Marking(mark, new Rgb(accent.R, accent.G, accent.B), dark, 0);
        if (next == marking)
        {
            return;
        }
        marking = next;
        _ = core.ExecuteScriptAsync(next.Script);
    }

    private void ReportWidth()
    {
        if (sheet is not null && SheetHtml.PagesWidth(ActualWidth) is { } width)
        {
            sheet.Resize(width);
        }
    }

    /// <summary>The model's pages in the window's theme: the first load serves the whole
    /// document, later pages replace its content, so the sheet keeps its place.</summary>
    private void Show()
    {
        if (sheet is null || Web.CoreWebView2 is not { } core || navigating)
        {
            return;
        }
        var content = SheetHtml.Sheets(sheet.Pages, ActualTheme == ElementTheme.Dark);
        Desk.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Colour(SheetHtml.Desk(ActualTheme == ElementTheme.Dark)));
        core.Profile.PreferredColorScheme = ActualTheme == ElementTheme.Dark ? CoreWebView2PreferredColorScheme.Dark : CoreWebView2PreferredColorScheme.Light;
        if (content == shown)
        {
            return;
        }
        shown = content;
        if (!loaded)
        {
            document = Encoding.UTF8.GetBytes(content.Document);
            navigating = true;
            core.Navigate(SheetHtml.Address);
            return;
        }
        _ = core.ExecuteScriptAsync(content.Replace);
        marking = null; // the new pages have no marker yet
        Mark();
    }

    private void Label() =>
        AutomationProperties.SetName(Web, sheet is { Pages.Count: > 0 } ? SheetHtml.Label(title, sheet.Pages.Count, strings) : "");

    private void Step(string message)
    {
        switch (message)
        {
            case "zoom_in":
                sheet?.ZoomIn();
                break;
            case "zoom_out":
                sheet?.ZoomOut();
                break;
            default:
                if (sheet is not null && SheetHtml.BarOfClick(message, sheet.Pages) is { } bar)
                {
                    playback?.Jump(bar);
                }
                else if (SheetHtml.KeyOfMessage(message) is { } key)
                {
                    pressed(key);
                }
                break;
        }
    }

    /// <summary>Writes the PDF (scope 4): <paramref name="html"/>, the A4 document, printed to
    /// <paramref name="path"/> on A4 without margins, header or footer. False when WebView2
    /// could not write it, or did not within a minute (the reader is told then, instead of a
    /// flow that waits for ever).</summary>
    public async Task<bool> PrintAsync(string html, string path)
    {
        if (printing is { IsCompleted: false })
        {
            return false; // the last one still runs (it ran out of time): WebView2 prints one at a time
        }
        var work = PrintingAsync(html, path);
        printing = work;
        var finished = await Task.WhenAny(work, Task.Delay(TimeSpan.FromMinutes(1)));
        return finished == work && await work;
    }

    private async Task<bool> PrintingAsync(string html, string path)
    {
        await Printer.EnsureCoreWebView2Async(await Environment());
        var core = Printer.CoreWebView2;
        if (printed is null)
        {
            Lock(core.Settings);
            core.AddWebResourceRequestedFilter(SheetHtml.Address + "*", CoreWebView2WebResourceContext.All);
            core.WebResourceRequested += (_, e) => Serve(core, e, printDocument);
            core.NavigationStarting += (_, e) =>
            {
                e.Cancel = e.Uri != PrintAddress;
                if (!e.Cancel)
                {
                    printNavigation = e.NavigationId;
                }
            };
            core.NavigationCompleted += (_, e) =>
            {
                if (e.NavigationId == printNavigation)
                {
                    printed?.TrySetResult(e.IsSuccess);
                }
            };
        }
        printDocument = Encoding.UTF8.GetBytes(html);
        // the print goes on after NavigationCompleted has returned, not inside it: WebView2 is
        // not to be called back from within its own event
        printed = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        core.Navigate(PrintAddress);
        if (!await printed.Task)
        {
            return false;
        }
        var settings = core.Environment.CreatePrintSettings();
        settings.Orientation = CoreWebView2PrintOrientation.Portrait;
        settings.PageWidth = 8.27; // A4 in inches
        settings.PageHeight = 11.69;
        settings.MarginTop = settings.MarginBottom = settings.MarginLeft = settings.MarginRight = 0;
        settings.ShouldPrintHeaderAndFooter = false;
        settings.ShouldPrintBackgrounds = true;
        settings.ScaleFactor = 1;
        return await core.PrintToPdfAsync(path, settings);
    }

    private static Windows.UI.Color Colour(string hex) => Windows.UI.Color.FromArgb(
        255,
        Convert.ToByte(hex[1..3], 16),
        Convert.ToByte(hex[3..5], 16),
        Convert.ToByte(hex[5..7], 16));
}
