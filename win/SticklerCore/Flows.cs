namespace Stickler.Core;

/// <summary>What only Windows can answer: the file dialogs, the questions, Explorer and
/// "Open with". The app answers with WinUI; the tests with a fake.</summary>
public interface IAsk
{
    /// <summary>Where to save <paramref name="name"/>; one of <paramref name="endings"/>
    /// (without the dot) when given. Null when the reader cancels.</summary>
    Task<string?> SaveFileAsync(string name, IReadOnlyList<string> endings);

    /// <summary>A file to open, of <paramref name="endings"/> (all files when empty).</summary>
    Task<string?> OpenFileAsync(IReadOnlyList<string> endings);

    /// <summary>A question with a main button and Cancel; true for the main button.</summary>
    Task<bool> ConfirmAsync(string title, string text, string action);

    /// <summary>A question with a checkbox: null for Cancel, else whether the box was ticked.</summary>
    Task<bool?> ConfirmWithBoxAsync(string title, string text, string action, string box);

    /// <summary>Windows' "Open with" chooser for <paramref name="file"/>.</summary>
    Task OpenWithAsync(string file);
}

/// <summary>The flows of the File and Export menus (SPEC.md, module <c>win-shell</c>, scope 2):
/// the questions and dialogs in the order the Mac and GTK apps ask them; the core does the work.</summary>
public sealed class Flows
{
    /// <summary>What a drum track can be saved as: the app's ffmpeg writes these (as on the Mac).</summary>
    public static readonly IReadOnlyList<string> DrumTrackEndings = ["flac", "wav"];

    /// <summary>The song files Stickler opens (<c>paths.AUDIO_SUFFIXES</c>).</summary>
    public static readonly IReadOnlyList<string> SongEndings = ["mp3", "flac", "wav", "ogg", "oga", "opus", "m4a", "aac", "aif", "aiff"];

    private readonly AppModel model;
    private readonly IAsk ask;
    private readonly Strings strings;

    public Flows(AppModel model, IAsk ask, Strings strings)
    {
        this.model = model;
        this.ask = ask;
        this.strings = strings;
    }

    /// <summary>The result being shown, if it can be exported (not while a correction's notes
    /// are written).</summary>
    public ResultScreen? Result =>
        model.State is { Screen: ResultScreen result, Can.Export: true } && !result.Correcting ? result : null;

    public async Task OpenSongAsync()
    {
        if (await ask.OpenFileAsync(SongEndings).ConfigureAwait(true) is { } song)
        {
            model.Open(song);
        }
    }

    public async Task ExportMusicXmlAsync()
    {
        if (Result is { } result
            && await ask.SaveFileAsync(WindowView.MusicXmlName(result.Song), ["musicxml"]).ConfigureAwait(true) is { } dest)
        {
            model.ExportMusicXml(dest);
        }
    }

    /// <summary>The cost first (Demucs may be downloaded before), then where to save.</summary>
    public async Task ExportDrumTrackAsync()
    {
        if (Result is not { } result || await model.DrumTrackCostAsync().ConfigureAwait(true) is not { } cost)
        {
            return;
        }
        var go = await ask.ConfirmAsync(
            strings.Text("Save the Drum Track?"), cost.Text, strings.Text("Choose Where to Save…")).ConfigureAwait(true);
        if (go && await ask.SaveFileAsync(WindowView.DrumTrackName(result.Song, strings), DrumTrackEndings).ConfigureAwait(true) is { } dest)
        {
            model.ExportDrumTrack(dest);
        }
    }

    /// <summary>Sheet Music (PDF)… (module <c>win-sheet</c>, scope 4): where to save, the core's
    /// A4 pages, then <paramref name="print"/> writes them to a file of its own beside the chosen
    /// one (so the move is a rename on the same drive, and the file gets that folder's
    /// permissions), which takes the chosen file's place only when it is whole: a failure leaves
    /// no half file and keeps one that was there. <paramref name="print"/> is WebView2's in the
    /// app; false or an exception is told with its reason, never ends the app.</summary>
    public async Task ExportPdfAsync(Func<A4Pages, string, Task<bool>> print)
    {
        ArgumentNullException.ThrowIfNull(print);
        if (Result is not { } result
            || await ask.SaveFileAsync(WindowView.PdfName(result.Song), ["pdf"]).ConfigureAwait(true) is not { } dest)
        {
            return;
        }
        A4Pages? pages;
        try
        {
            pages = await model.A4PagesAsync().ConfigureAwait(true);
        }
        catch (UnreadableLineException error)
        {
            model.Tell(new Notice(strings.Text("Could not save: {reason}", ("reason", error.Message)), null));
            return;
        }
        if (pages is null)
        {
            return;
        }
        var part = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(dest))!, $".{Path.GetFileName(dest)}.{Guid.NewGuid():N}.part");
        try
        {
            if (!await print(pages, part).ConfigureAwait(true))
            {
                // Windows' own words for a write that failed (ERROR_WRITE_FAULT), in its language
                throw new IOException(new System.ComponentModel.Win32Exception(29).Message);
            }
            File.Move(part, dest, overwrite: true);
            model.Tell(new Notice(strings.Text("Saved “{name}”", ("name", Path.GetFileName(dest))), dest));
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException or ArgumentException or System.Runtime.InteropServices.COMException)
        {
            model.Tell(new Notice(strings.Text("Could not save: {reason}", ("reason", error.Message)), null));
        }
        finally
        {
            try
            {
                File.Delete(part);
            }
            catch (Exception locked) when (locked is IOException or UnauthorizedAccessException)
            {
                // a print that ran out of time may still hold it: the leftover is only ours
            }
        }
    }

    /// <summary>The MusicXML in a program the reader picks.</summary>
    public async Task OpenWithAsync()
    {
        if (Result is { } result)
        {
            await ask.OpenWithAsync(result.MusicXml).ConfigureAwait(true);
        }
    }

    public async Task BackUpAsync(DateOnly today)
    {
        if (await ask.SaveFileAsync(WindowView.BackupName(today), ["zip"]).ConfigureAwait(true) is { } dest)
        {
            model.BackUp(dest);
        }
    }

    /// <summary>Which file, then the question with what it holds; the core restores it.</summary>
    public async Task RestoreAsync()
    {
        if (await ask.OpenFileAsync(["zip"]).ConfigureAwait(true) is not { } src
            || await model.BackupSummaryAsync(src).ConfigureAwait(true) is not { } summary)
        {
            return;
        }
        if (await ask.ConfirmAsync(strings.Text("Restore Backup?"), summary.Text, strings.Text("Restore")).ConfigureAwait(true))
        {
            model.Restore(src);
        }
    }

    /// <summary>The sizes first, then the question with the checkbox for everything else.</summary>
    public async Task RemoveModelsAsync()
    {
        if (await model.RemovalSizesAsync().ConfigureAwait(true) is not { } sizes)
        {
            return;
        }
        var everything = await ask.ConfirmWithBoxAsync(
            strings.Text("Remove Downloaded Models?"),
            sizes.ModelsText,
            strings.Text("Remove"),
            strings.Text("Also remove settings, recent songs and corrections")).ConfigureAwait(true);
        if (everything is { } all)
        {
            model.RemoveModels(all);
        }
    }
}
