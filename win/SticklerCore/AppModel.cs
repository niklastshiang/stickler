using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Threading.Channels;

namespace Stickler.Core;

public enum Phase
{
    /// <summary>Before <see cref="AppModel.Launch"/>: no core yet, and nothing to show.</summary>
    Launching,
    Running,

    /// <summary>The core ended or did not start: the page "Stickler Stopped Unexpectedly".</summary>
    Stopped,
}

/// <summary>The window's model (SPEC.md, module <c>win-shell</c>): the core's latest state, the
/// recent songs, the newest notice, and whether the core runs. It forwards every action as
/// one command and decides no flow itself; the core does. Its properties change on the thread
/// <c>post</c> runs work on (the window's), in the core's order.</summary>
public sealed class AppModel : INotifyPropertyChanged
{
    private readonly IReadOnlyList<string> languages;
    private readonly Func<IReadOnlyList<string>, ICore> makeCore;
    private readonly Action<Action> post;
    private ICore? core;
    private Channel<Command>? outbox;
    private int lastSeq;
    private Phase phase = Phase.Launching;
    private CoreEnd? end;
    private AppState state = AppState.Empty;
    private IReadOnlyList<RecentRow> recent = [];
    private Notice? notice;
    private int noticeSerial;
    private string? language;
    private string? version;

    /// <summary><paramref name="makeCore"/> builds a core for the reader's languages;
    /// <paramref name="post"/> runs work on the window's thread, in order (the dispatcher queue);
    /// <paramref name="player"/> plays the shown result (<c>null</c>: nothing can play).</summary>
    public AppModel(
        IReadOnlyList<string> languages,
        Func<IReadOnlyList<string>, ICore> makeCore,
        Action<Action> post,
        IPlaying? player = null)
        : this(languages, makeCore, post, TimeSpan.FromSeconds(0.3), player)
    {
    }

    /// <summary><paramref name="settle"/>: how long the sheet's width must hold before its
    /// pages are asked for again (<see cref="SheetModel"/>); <paramref name="ticker"/> reads the
    /// player's position while playing (default: every 50 ms, <see cref="PlaybackModel.Every"/>).</summary>
    public AppModel(
        IReadOnlyList<string> languages,
        Func<IReadOnlyList<string>, ICore> makeCore,
        Action<Action> post,
        TimeSpan settle,
        IPlaying? player = null,
        Ticker? ticker = null)
    {
        this.languages = languages;
        this.makeCore = makeCore;
        this.post = post;
        Sheet = new SheetModel(post, settle, error => Notice = new Notice(error.Message, null));
        Playback = new PlaybackModel(player, ticker ?? PlaybackModel.Every(TimeSpan.FromMilliseconds(50), post), post, Tell);
    }

    /// <summary>The sheet music of the shown result (module <c>win-sheet</c>).</summary>
    public SheetModel Sheet { get; }

    /// <summary>Playing the shown result (module <c>win-playback</c>).</summary>
    public PlaybackModel Playback { get; }

    public event PropertyChangedEventHandler? PropertyChanged;

    public Phase Phase { get => phase; private set => Set(ref phase, value); }

    /// <summary>How the core ended, while <see cref="Phase"/> is <see cref="Phase.Stopped"/>.</summary>
    public CoreEnd? End { get => end; private set => Set(ref end, value); }

    public AppState State
    {
        get => state;
        private set
        {
            if (Set(ref state, value))
            {
                Changed(nameof(Title));
                Changed(nameof(Subtitle));
            }
        }
    }

    public IReadOnlyList<RecentRow> Recent { get => recent; private set => Set(ref recent, value); }

    /// <summary>The newest notice; the window shows it until it is dismissed or a newer one comes.</summary>
    public Notice? Notice
    {
        get => notice;
        private set
        {
            notice = value;
            NoticeSerial++;
            Changed();
        }
    }

    /// <summary>Counts the notices, so a second one that says the same is shown again.</summary>
    public int NoticeSerial { get => noticeSerial; private set => Set(ref noticeSerial, value); }

    /// <summary>The core's language (<c>hello</c>).</summary>
    public string? Language { get => language; private set => Set(ref language, value); }

    /// <summary>The core's release (<c>hello</c>), for About Stickler.</summary>
    public string? Version { get => version; private set => Set(ref version, value); }

    /// <summary>The header's title: the song once it has one, else the app.</summary>
    public string Title => State.Screen switch
    {
        ResultScreen result => result.Title,
        ExportingScreen exporting => exporting.Title,
        AnalysingScreen analysing => analysing.Name,
        FailedScreen failed => failed.Name,
        _ => "Stickler",
    };

    /// <summary>The line under the title: artist, tempo and time signature of a result.</summary>
    public string Subtitle => State.Screen switch
    {
        ResultScreen result => result.Subtitle,
        ExportingScreen exporting => exporting.Subtitle,
        _ => "",
    };

    // the core

    /// <summary>At launch: the app's core starts.</summary>
    public void Launch() => StartCore(makeCore(languages));

    /// <summary>"Start Again" on the stopped page: a new core.</summary>
    public void StartAgain() => StartCore(makeCore(languages));

    /// <summary>Quitting: the core ends politely (at most 3 s, then it is ended).</summary>
    public Task QuitAsync() => LetGo() is { } old ? old.QuitAsync(3) : Task.CompletedTask;

    private ICore? LetGo()
    {
        outbox?.Writer.TryComplete();
        outbox = null;
        var old = core;
        core = null;
        return old;
    }

    private void StartCore(ICore next)
    {
        // a core still running is told to quit: two cores would share the same folders
        if (LetGo() is { } old)
        {
            _ = old.QuitAsync(3);
        }
        core = next;
        lastSeq = 0;
        State = AppState.Empty;
        Notice = null;
        End = null;
        Phase = Phase.Running;
        // one sender keeps the reader's order
        var commands = Channel.CreateUnbounded<Command>(new UnboundedChannelOptions { SingleReader = true });
        outbox = commands;
        _ = Task.Run(async () =>
        {
            await foreach (var command in commands.Reader.ReadAllAsync().ConfigureAwait(false))
            {
                try
                {
                    await next.SendAsync(command).ConfigureAwait(false);
                }
                catch (CoreRefusedException refusal)
                {
                    post(() => Refused(refusal, next));
                }
                catch (CoreNotRunningException)
                {
                    // the stopped page follows through onEnd
                }
            }
        });
        next.Start(
            incoming => post(() => Handle(incoming, next)),
            how => post(() => Ended(how, next)));
        Send(Command.Start);
        Sheet.Attach(next);
        Playback.Attach(next);
    }

    private void Handle(Incoming incoming, ICore source)
    {
        if (!ReferenceEquals(source, core))
        {
            return; // a core replaced by "Start Again"
        }
        switch (incoming)
        {
            case HelloLine hello:
                Language = hello.Hello.Language;
                Version = hello.Hello.Version;
                break;
            case StateEvent e when Fresh(e.Seq):
                State = e.State;
                Sheet.Show(e.State.Screen);
                Playback.Show(e.State.Screen);
                break;
            case RecentEvent e when Fresh(e.Seq):
                Recent = e.Rows;
                break;
            case NoticeEvent e when Fresh(e.Seq):
                Notice = e.Notice;
                break;
            case UnknownEvent e:
                Fresh(e.Seq);
                break;
            default:
                break; // a late event, or a reply (they go to their SendAsync)
        }
    }

    private bool Fresh(int seq)
    {
        if (seq <= lastSeq)
        {
            return false;
        }
        lastSeq = seq;
        return true;
    }

    private void Ended(CoreEnd how, ICore source)
    {
        if (!ReferenceEquals(source, core))
        {
            return;
        }
        LetGo();
        Sheet.Attach(null);
        Playback.Attach(null);
        End = how;
        Phase = Phase.Stopped;
    }

    // what the reader does: one command each

    public void Open(string path) => Send(Command.Open(path));

    public void Cancel() => Send(Command.Cancel);

    public void Retry() => Send(Command.Retry);

    public void Close() => Send(Command.Close);

    public void Agree() => Send(Command.Agree);

    public void NotNow() => Send(Command.NotNow);

    public void RetrySetup() => Send(Command.RetrySetup);

    public void Forget(string path) => Send(Command.ForgetRecent(path));

    public void ExportMusicXml(string dest) => Send(Command.ExportMusicXml(dest));

    public void ExportDrumTrack(string dest) => Send(Command.ExportDrumTrack(dest));

    public void RemoveModels(bool everything)
    {
        Playback.LetGo(); // the core deletes the cache, where the player's files are
        Send(Command.RemoveModels(everything));
    }

    public void BackUp(string dest) => Send(Command.BackUp(dest));

    public void Restore(string src) => Send(Command.Restore(src));

    /// <summary>One change from the corrections controls; the core shows the new values at once
    /// and a refusal is the window's notice. A stepper sends steps (<c>BeatsPerBarBy</c>), which
    /// the core counts from its newest values, so two quick clicks make two steps.</summary>
    public void Correct(Correction change) => Send(Command.Correct(change));

    /// <summary>File › Open Recent › Clear Menu: every recent song forgotten.</summary>
    public void ClearRecent()
    {
        foreach (var row in Recent)
        {
            Forget(row.Path);
        }
    }

    /// <summary>A notice of the app's own, shown like the core's.</summary>
    public void Tell(Notice note) => Notice = note;

    public void DismissNotice() => Notice = null;

    /// <summary>What saving the drum track costs, for the dialog before it starts.</summary>
    public Task<DrumTrackCost?> DrumTrackCostAsync() => AskAsync(Command.DrumTrackCost, DrumTrackCost.From);

    /// <summary>What a backup holds and the restore's question; null (with the core's reason
    /// as the notice) when the file is no backup.</summary>
    public Task<BackupSummary?> BackupSummaryAsync(string src) => AskAsync(Command.BackupSummary(src), BackupSummary.From);

    /// <summary>The result's A4 pages and title, for the PDF the app writes (module <c>win-sheet</c>).</summary>
    public Task<A4Pages?> A4PagesAsync() => AskAsync(Command.A4Pages, A4Pages.From);

    /// <summary>What "Remove Downloaded Models…" frees, for its dialog.</summary>
    public Task<RemovalSizes?> RemovalSizesAsync() => AskAsync(Command.RemovalSizes, RemovalSizes.From);

    /// <summary>What "Uninstall Stickler…" frees, for its dialog.</summary>
    public Task<UninstallSizes?> UninstallSizesAsync() => AskAsync(Command.UninstallSizes, UninstallSizes.From);

    /// <summary>Removes Stickler's folders through the core; true once they are gone.</summary>
    public async Task<bool> UninstallAsync(bool everything)
    {
        Playback.LetGo(); // the core deletes the cache, where the player's files are
        return await AskAsync(Command.Uninstall(everything), reply => reply).ConfigureAwait(true) is not null;
    }

    private void Send(Command command) => outbox?.Writer.TryWrite(command);

    private async Task<T?> AskAsync<T>(Command command, Func<Reply, T> read)
        where T : class
    {
        if (core is not { } asked)
        {
            return null;
        }
        try
        {
            return read(await asked.SendAsync(command).ConfigureAwait(true));
        }
        catch (CoreRefusedException refusal)
        {
            Refused(refusal, asked);
            return null;
        }
        catch (CoreNotRunningException)
        {
            return null;
        }
    }

    /// <summary>A refused command says why (translated by the core).</summary>
    private void Refused(CoreRefusedException refusal, ICore source)
    {
        if (ReferenceEquals(source, core))
        {
            Notice = new Notice(refusal.Error.Message, null);
        }
    }

    private bool Set<T>(ref T field, T value, [CallerMemberName] string? name = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
        {
            return false;
        }
        field = value;
        Changed(name);
        return true;
    }

    private void Changed([CallerMemberName] string? name = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}
