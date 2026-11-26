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
/// (a touchpad's pinch arrives as one) into the core's zoom steps. A pure view: checked by
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
    private Strings strings = Strings.English;
    private string title = "";
    private Task<CoreWebView2Environment>? environment;
    private byte[] document = [];
    private byte[] printDocument = [];
    private bool loaded; // the document is there: new pages replace its content
    private bool navigating;
    private SheetHtml.Content? shown;
    private TaskCompletionSource<bool>? printed;

    public SheetView()
    {
        InitializeComponent();
        SizeChanged += (_, _) => ReportWidth();
        ActualThemeChanged += (_, _) => Show();
    }

    /// <summary>Where WebView2 keeps its data: under Stickler's folder, not next to the .exe
    /// (an installed app's folder is the program's), removed with Stickler's data.</summary>
    public static string DataFolder =>
        Path.Combine(System.Environment.GetFolderPath(System.Environment.SpecialFolder.LocalApplicationData), "Stickler", "WebView2");

    /// <summary>Starts the view on <paramref name="model"/>'s pages.</summary>
    public void Attach(SheetModel model, Strings words)
    {
        sheet = model;
        strings = words;
        sheet.PropertyChanged += OnSheetChanged;
        _ = StartAsync();
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
        core.Settings.IsWebMessageEnabled = true; // the wheel script's steps
        await core.AddScriptToExecuteOnDocumentCreatedAsync(WheelScript);
        core.AddWebResourceRequestedFilter(SheetHtml.Address + "*", CoreWebView2WebResourceContext.All);
        core.WebResourceRequested += (_, e) => Serve(core, e, document);
        core.NavigationStarting += (_, e) => e.Cancel = e.Uri != SheetHtml.Address;
        core.NewWindowRequested += (_, e) => e.Handled = true;
        core.NavigationCompleted += (_, e) =>
        {
            navigating = false;
            loaded = e.IsSuccess;
            Show(); // pages that came while it loaded
        };
        core.WebMessageReceived += (_, e) => Step(e.TryGetWebMessageAsString());
        ReportWidth();
        Show();
    }

    /// <summary>What the page may do: nothing but show the pages.</summary>
    private static void Lock(CoreWebView2Settings settings)
    {
        settings.IsScriptEnabled = false; // the app's own scripts still run
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
    }

    private void Label() =>
        AutomationProperties.SetName(Web, sheet is null ? "" : SheetHtml.Label(title, sheet.Pages.Count, strings));

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
                break;
        }
    }

    /// <summary>Writes the PDF (scope 4): <paramref name="html"/>, the A4 document, printed to
    /// <paramref name="path"/> on A4 without margins, header or footer. False when WebView2
    /// could not write it, or did not within a minute (the reader is told then, instead of a
    /// flow that waits for ever).</summary>
    public async Task<bool> PrintAsync(string html, string path)
    {
        var work = PrintingAsync(html, path);
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
            core.NavigationStarting += (_, e) => e.Cancel = e.Uri != PrintAddress;
            core.NavigationCompleted += (_, e) => printed?.TrySetResult(e.IsSuccess);
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
