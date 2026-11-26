using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace Stickler.Core;

/// <summary>The sheet music's model (SPEC.md, module <c>win-sheet</c>, scope 1), as the Mac's
/// <c>SheetModel</c>: which pages to ask the core for and when, and which reply wins. The view
/// only draws <see cref="Pages"/> and reports its width; the note size is the core's setting.
/// Its properties change on the thread <c>post</c> runs work on (the window's).</summary>
public sealed class SheetModel : INotifyPropertyChanged
{
    private readonly Action<Action> post;
    private readonly TimeSpan settle;
    private readonly Action<BridgeError> refused;
    private ICore? core;
    private Music? music;
    private bool onScreen; // the result is shown, not an export's steps
    private bool owed; // pages wanted while they could not be asked for
    private double? width;
    private CancellationTokenSource? settling;
    private int request; // the newest request's number; older replies are dropped
    private IReadOnlyList<SheetPage> pages = [];
    private double zoom = 1.0;
    private string percent = "100%";
    private bool canZoom;

    /// <summary><paramref name="settle"/>: how long a width must hold before it counts (the
    /// GTK app's pause after a resize). <paramref name="refused"/> tells the reader why a
    /// command was refused.</summary>
    public SheetModel(Action<Action> post, TimeSpan settle, Action<BridgeError> refused)
    {
        this.post = post;
        this.settle = settle;
        this.refused = refused;
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    /// <summary>The shown result's pages at the sheet's width; the old ones stay while new ones come.</summary>
    public IReadOnlyList<SheetPage> Pages { get => pages; private set => Set(ref pages, value); }

    /// <summary>The note size, 1 is 100 %.</summary>
    public double Zoom { get => zoom; private set => Set(ref zoom, value); }

    /// <summary>The note size as the menu shows it.</summary>
    public string Percent { get => percent; private set => Set(ref percent, value); }

    /// <summary>Whether a result is shown, so the zoom entries are enabled. Not while its drum
    /// track is saved: the steps are shown then, and the core engraves nothing.</summary>
    public bool CanZoom { get => canZoom; private set => Set(ref canZoom, value); }

    /// <summary>A new core (or none): the sheet starts empty and asks for the stored note size.</summary>
    public void Attach(ICore? next)
    {
        core = next;
        music = null;
        owed = false;
        Showing(false);
        Pages = [];
        request++;
        settling?.Cancel();
        if (next is null)
        {
            return;
        }
        _ = Ask(next, Command.Settings, SheetSettings.From, settings =>
        {
            Zoom = settings.Zoom;
            Percent = settings.Percent;
        });
    }

    /// <summary>The core's new state: a new result asks for its pages, an export keeps them,
    /// any other screen empties the sheet.</summary>
    public void Show(Screen screen)
    {
        switch (screen)
        {
            case ResultScreen result:
                var next = new Music(result.Song, result.MusicXml, result.Sheet);
                var fresh = next != music || owed;
                music = next;
                Showing(true);
                if (fresh)
                {
                    AskForPages();
                }
                break;
            case ExportingScreen:
                Showing(false);
                break;
            default:
                music = null;
                owed = false;
                Showing(false);
                Pages = [];
                request++;
                break;
        }
    }

    /// <summary>The sheet's width in effective pixels: the first one counts at once, later
    /// ones once they held for the settle time.</summary>
    public void Resize(double next)
    {
        settling?.Cancel();
        settling = null;
        if (width is null)
        {
            width = next;
            AskForPages();
            return;
        }
        if (next == width)
        {
            return;
        }
        var wait = new CancellationTokenSource();
        settling = wait;
        _ = Task.Run(async () =>
        {
            try
            {
                await Task.Delay(settle, wait.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                return;
            }
            post(() =>
            {
                if (wait.IsCancellationRequested)
                {
                    return;
                }
                width = next;
                AskForPages();
            });
        });
    }

    /// <summary>View › Zoom In (Ctrl+Plus, Ctrl+wheel up).</summary>
    public void ZoomIn() => Change(Command.ZoomIn);

    /// <summary>View › Zoom Out (Ctrl+Minus, Ctrl+wheel down).</summary>
    public void ZoomOut() => Change(Command.ZoomOut);

    /// <summary>View › Actual Size (Ctrl+0).</summary>
    public void ActualSize() => Change(Command.ActualSize);

    /// <summary>A note size of the reader's choice; the core keeps it within its limits.</summary>
    public void SetZoom(double size) => Change(Command.SetZoom(size));

    private void Change(Command command)
    {
        if (core is not { } asked)
        {
            return;
        }
        _ = Ask(asked, command, Core.Zoom.From, next =>
        {
            Zoom = next.Size;
            Percent = next.Percent;
            AskForPages();
        });
    }

    private void AskForPages()
    {
        if (core is not { } asked || music is null || width is not { } wide)
        {
            return;
        }
        if (!onScreen)
        {
            owed = true; // asked for when the result is back
            return;
        }
        owed = false;
        var mine = ++request;
        _ = Ask(asked, Command.Pages(wide), Core.Pages.From, next =>
        {
            if (mine != request)
            {
                return;
            }
            Pages = next.Sheets;
            Zoom = next.Zoom;
        }, () => mine == request);
    }

    /// <summary>Sends <paramref name="command"/>; its reply is used on the window's thread while
    /// <paramref name="asked"/> is still the core (and <paramref name="current"/> holds), a
    /// refusal is told the same way.</summary>
    private async Task Ask<T>(ICore asked, Command command, Func<Reply, T> read, Action<T> use, Func<bool>? current = null)
    {
        try
        {
            var reply = read(await asked.SendAsync(command).ConfigureAwait(false));
            post(() =>
            {
                if (ReferenceEquals(asked, core))
                {
                    use(reply);
                }
            });
        }
        catch (CoreRefusedException refusal)
        {
            post(() =>
            {
                if (ReferenceEquals(asked, core) && (current?.Invoke() ?? true))
                {
                    refused(refusal.Error);
                }
            });
        }
        catch (CoreNotRunningException)
        {
            // the stopped page follows through the app's model
        }
        catch (UnreadableLineException)
        {
            // a reply without the fields this release reads: the sheet stays as it is
        }
    }

    private void Showing(bool shown)
    {
        onScreen = shown;
        CanZoom = shown && music is not null;
    }

    private bool Set<T>(ref T field, T value, [CallerMemberName] string? name = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
        {
            return false;
        }
        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
        return true;
    }

    /// <summary>What decides the pages of a result: a correction's new notation changes it
    /// (<c>sheet</c>), its start does not (the notes are still the old ones then), nor does an export.</summary>
    private sealed record Music(string Song, string MusicXml, int Sheet);
}
