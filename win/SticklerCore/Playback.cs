using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace Stickler.Core;

/// <summary>Why the player paused by itself.</summary>
public enum PlayerPause
{
    /// <summary>The song played to its end.</summary>
    Ended,

    /// <summary>The sound output changed (headphones unplugged, another device): paused, not lost.</summary>
    Interrupted,
}

/// <summary>What the player cannot do; its message is shown as the window's notice.</summary>
public abstract class PlayerException : Exception
{
    protected PlayerException(string message) : base(message)
    {
    }
}

/// <summary>The system cannot read the file's format: the core decodes a copy of a song
/// (<c>playable</c>); the message is shown when the copy cannot be read either.</summary>
public sealed class PlayerUnreadableException : PlayerException
{
    public PlayerUnreadableException(string message) : base(message)
    {
    }
}

/// <summary>Anything else (no sound device, a broken file), said in words for the reader.</summary>
public sealed class PlayerFailedException : PlayerException
{
    public PlayerFailedException(string message) : base(message)
    {
    }
}

/// <summary>What plays the sound (the app's Windows player, <c>ui/player.py</c> in GTK; a fake in
/// tests): the song and the clicks together on one clock. Its methods are called on the window's
/// thread.</summary>
public interface IPlaying
{
    /// <summary>Told when it paused by itself (on any thread).</summary>
    event Action<PlayerPause>? Paused;

    /// <summary>Where it is now, in seconds of the song.</summary>
    double Position { get; }

    /// <summary>Loads the song and, when there is one, the clicks; stopped at 0. Throws a
    /// <see cref="PlayerException"/>.</summary>
    void Load(string song, string? clicks);

    void Play();

    void Pause();

    void Seek(double seconds);

    void SetGains(Gains gains);

    /// <summary>Lets go of everything: nothing plays or holds the sound device any more.</summary>
    void Release();
}

/// <summary>Starts calling <c>tick</c> every so often until the result is disposed.</summary>
public delegate IDisposable Ticker(Action tick);

/// <summary>Playback (SPEC.md, "Mac playback" scope 2 and "<c>win-playback</c>" scope 1; GTK's
/// <c>ui/playbar.py</c>): the controls' state and what each control does. The core decides where
/// a click or an arrow goes and how loud each source plays; this model asks it and drives the
/// player. Like the sheet, it changes its properties on the thread <c>post</c> runs work on (the
/// window's), and every public method is called there.</summary>
public sealed class PlaybackModel : INotifyPropertyChanged
{
    private readonly IPlaying? player;
    private readonly Ticker ticker;
    private readonly Action<Action> post;
    private readonly Action<Notice> tell;
    private readonly Lane moves = new(); // the `step`s and `jump`s, sent in order
    private readonly Lane volumes = new(); // the `volumes` commands, sent in order
    private readonly Lane reads = new(); // the stored volumes' reads, one per core
    private ICore? core;
    private string? song;
    private string? clicks;
    private bool onScreen; // the result is shown, not an export's steps
    private bool loaded; // the player holds this song
    private bool atEnd; // played to the end: play starts again at 0
    private bool starting; // a play waits for the core (a copy, the gains)
    private bool called; // a second press called off a play that still waits
    private Gains? gains; // the core's newest answer
    private int volumeRequest; // older answers are dropped
    private object? tickToken;
    private IDisposable? ticking;
    private bool playing;
    private double position;
    private double length;
    private IReadOnlyList<SongBar> bars = [];
    private Hear hear = Hear.Both;
    private double songVolume = 0.7;
    private double hitsVolume = 1.0;
    private int? marked;

    /// <summary>How close to the length the position must be for an end to count (seconds): the
    /// player's length and the core's can differ by a few frames.</summary>
    private const double EndMargin = 0.25;

    /// <summary><paramref name="player"/> is <c>null</c> when nothing can play (the controls stay
    /// off). <paramref name="ticker"/> reads the position while playing (GTK: every 50 ms,
    /// <see cref="Every"/>). <paramref name="tell"/> shows a notice in the window.</summary>
    public PlaybackModel(IPlaying? player, Ticker ticker, Action<Action> post, Action<Notice> tell)
    {
        this.player = player;
        this.ticker = ticker;
        this.post = post;
        this.tell = tell;
        if (player is not null)
        {
            player.Paused += why => post(() => PausedByItself(why));
        }
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public bool Playing { get => playing; private set => Set(ref playing, value); }

    /// <summary>Where the song is, in seconds.</summary>
    public double Position
    {
        get => position;
        private set
        {
            if (Set(ref position, value))
            {
                Changed(nameof(Time));
                Changed(nameof(Label));
            }
            Follow();
        }
    }

    /// <summary>The song's length in seconds.</summary>
    public double Length
    {
        get => length;
        private set
        {
            if (Set(ref length, value))
            {
                Changed(nameof(LengthText));
            }
        }
    }

    /// <summary>The song's bars in played order.</summary>
    public IReadOnlyList<SongBar> Bars
    {
        get => bars;
        private set
        {
            bars = value;
            Changed();
            Changed(nameof(Label));
            Follow();
        }
    }

    public Hear Hear { get => hear; private set => Set(ref hear, value); }

    /// <summary>The volume slider of the song, 0 to 1 (remembered by the core for every song).</summary>
    public double SongVolume { get => songVolume; private set => Set(ref songVolume, value); }

    /// <summary>The volume slider of the detected hits, 0 to 1.</summary>
    public double HitsVolume { get => hitsVolume; private set => Set(ref hitsVolume, value); }

    /// <summary>A result is shown and there is a player: the controls and the Controls menu work.</summary>
    public bool CanPlay => song is not null && onScreen && player is not null;

    /// <summary>"Bar 2 of 110".</summary>
    public string Label => Timeline.Label(bars, position);

    /// <summary>"0:06".</summary>
    public string Time => Timeline.Clock(position);

    /// <summary>"4:06".</summary>
    public string LengthText => Timeline.Clock(length);

    /// <summary>The written bar to mark on the sheet; <c>null</c> when none sounds. It changes only
    /// when the bar does, so the sheet is not drawn again at every tick.</summary>
    public int? Marked { get => marked; private set => Set(ref marked, value); }

    /// <summary>A play waits for the core (for the tests).</summary>
    internal bool Starting => starting;

    /// <summary>Done when the questions asked so far have been answered and acted on (for the tests;
    /// the work they post to the window is queued by then).</summary>
    internal Task Idle => Task.WhenAll(moves.Last, volumes.Last, reads.Last);

    private double Now => loaded && player is not null ? player.Position : position;

    /// <summary>A ticker that runs <c>tick</c> through <paramref name="post"/> every
    /// <paramref name="interval"/>.</summary>
    public static Ticker Every(TimeSpan interval, Action<Action> post) =>
        tick => new Timer(_ => post(tick), null, interval, interval);

    // what the app model tells it

    /// <summary>A new core (or none): nothing plays; the stored volumes are read.</summary>
    internal void Attach(ICore? next)
    {
        core = next;
        ForgetSong();
        gains = null;
        if (next is null || player is null)
        {
            return; // nothing can play: the volumes would not be heard
        }
        var asked = volumeRequest;
        _ = reads.Run(async () =>
        {
            if (await Request(next, Command.Settings, PlaybackSettings.From).ConfigureAwait(false) is { } settings)
            {
                post(() =>
                {
                    // a core replaced meanwhile, or a slider the reader moved before the answer
                    if (ReferenceEquals(next, core) && asked == volumeRequest)
                    {
                        SongVolume = settings.SongVolume;
                        HitsVolume = settings.HitsVolume;
                    }
                });
            }
        });
    }

    /// <summary>The core's new state: a new song starts stopped at 0; a correction of the same song
    /// goes on with its new bars; an export pauses; any other screen stops playback.</summary>
    internal void Show(Screen screen)
    {
        switch (screen)
        {
            case ResultScreen result:
                if (result.Song != song)
                {
                    ForgetSong();
                    Song = result.Song;
                    clicks = result.Clicks;
                }
                OnScreen = true;
                Bars = result.Bars;
                Length = result.Seconds;
                break;
            case ExportingScreen:
                OnScreen = false;
                if (playing)
                {
                    Pause();
                }
                break;
            default:
                ForgetSong();
                break;
        }
    }

    // what the reader does

    /// <summary>Play or Pause (Space).</summary>
    public void Toggle()
    {
        if (!CanPlay || core is not { } asked || player is not { } active || song is not { } wanted)
        {
            return;
        }
        if (playing)
        {
            Pause();
        }
        else if (starting)
        {
            called = true; // pressed again while it waits: it does not start
        }
        else
        {
            _ = Start(asked, active, wanted);
        }
    }

    /// <summary>Moves to <paramref name="seconds"/>, kept inside the song; playing goes on from there.</summary>
    public void Seek(double seconds)
    {
        if (song is null)
        {
            return;
        }
        var target = Math.Min(Math.Max(seconds, 0), length);
        atEnd = false;
        if (loaded && !Try(() => player?.Seek(target)))
        {
            // the device could not be opened again: stopped, where the player is now
            Playing = false;
            StopTicking();
            Position = Now;
            return;
        }
        Position = target;
    }

    /// <summary>Go to the Start (Alt+Left, Home).</summary>
    public void GoToStart()
    {
        if (CanPlay)
        {
            Seek(0);
        }
    }

    /// <summary>Previous Bar (Left).</summary>
    public void PreviousBar() => Step(-1);

    /// <summary>Next Bar (Right).</summary>
    public void NextBar() => Step(1);

    /// <summary>A click on written bar <paramref name="bar"/>: its next pass (the core's rule);
    /// stopped, the position moves there without playing.</summary>
    public void Jump(int bar)
    {
        if (CanPlay && core is { } asked && song is { } wanted)
        {
            Ask(asked, wanted, at => Command.Jump(bar, at));
        }
    }

    public void SetHear(Hear next)
    {
        Hear = next;
        _ = ChangeVolumes(null, null);
    }

    public void SetSongVolume(double value)
    {
        SongVolume = value;
        _ = ChangeVolumes(value, null);
    }

    public void SetHitsVolume(double value)
    {
        HitsVolume = value;
        _ = ChangeVolumes(null, value);
    }

    // the player

    private string? Song
    {
        set
        {
            song = value;
            Changed(nameof(CanPlay));
            Follow();
        }
    }

    private bool OnScreen
    {
        set
        {
            onScreen = value;
            Changed(nameof(CanPlay));
        }
    }

    private async Task Start(ICore asked, IPlaying player, string wanted)
    {
        starting = true;
        called = false;
        try
        {
            if (!loaded && !await Load(asked, wanted, player).ConfigureAwait(false))
            {
                return;
            }
            if (await OnWindow(() => gains is null).ConfigureAwait(false))
            {
                // started on the window's thread: it counts the requests and queues the command
                var changing = await OnWindow(() => ChangeVolumes(null, null)).ConfigureAwait(false);
                await changing.ConfigureAwait(false);
            }
            await OnWindow(() => Begin(wanted, player)).ConfigureAwait(false);
        }
        finally
        {
            await OnWindow(() =>
            {
                starting = false;
            }).ConfigureAwait(false);
        }
    }

    /// <summary>Plays from the position, unless the song was closed or the press called off.</summary>
    private void Begin(string wanted, IPlaying player)
    {
        if (wanted != song || !loaded || !onScreen || called)
        {
            return;
        }
        if (atEnd)
        {
            atEnd = false;
            Position = 0;
        }
        // An end told at once (nothing was left to play) comes through post, after this turn.
        if (!Try(() =>
        {
            player.Seek(position);
            player.Play();
        }))
        {
            return;
        }
        Playing = true;
        StartTicking();
    }

    /// <summary>Loads the song, or the core's copy when the system cannot read it; false when
    /// neither plays (the reader is told why).</summary>
    private async Task<bool> Load(ICore asked, string wanted, IPlaying player)
    {
        try
        {
            player.Load(wanted, clicks);
        }
        catch (PlayerUnreadableException)
        {
            var copy = await Request(asked, Command.Playable, Playable.From).ConfigureAwait(false);
            return copy is not null && await OnWindow(() => LoadCopy(wanted, copy.Path, player)).ConfigureAwait(false);
        }
        catch (PlayerException failure)
        {
            Failed(failure);
            return false;
        }
        return Loaded(player);
    }

    private bool LoadCopy(string wanted, string path, IPlaying player)
    {
        if (wanted != song)
        {
            return false;
        }
        try
        {
            player.Load(path, clicks);
        }
        catch (PlayerException failure)
        {
            Failed(failure);
            return false;
        }
        return Loaded(player);
    }

    private bool Loaded(IPlaying player)
    {
        loaded = true;
        if (gains is { } known)
        {
            _ = Try(() => player.SetGains(known));
        }
        return true;
    }

    private void Pause()
    {
        _ = Try(() => player?.Pause());
        Position = Now;
        Playing = false;
        StopTicking();
    }

    /// <summary>The player stopped by itself. Told through <c>post</c>, so it can come after the
    /// reader moved on: a stop with nothing playing (the song was closed or changed, the reader
    /// paused) is not about what is shown now, and an end counts only where the song ends (not
    /// when the reader seeked in the same turn).</summary>
    private void PausedByItself(PlayerPause why)
    {
        if (!loaded || !playing)
        {
            return;
        }
        Position = Now;
        Playing = false;
        StopTicking();
        if (why == PlayerPause.Ended && position >= length - EndMargin)
        {
            atEnd = true;
        }
    }

    /// <summary>Closes the player's files and stops; the song stays shown where it was, and the
    /// next Play loads it again. Before the core deletes Stickler's folders: the clicks (and the
    /// core's copy of a song) are in the cache, and Windows does not delete an open file (found
    /// in a VM on 2026-11-27: "Uninstall Stickler…" after playing left the program installed).</summary>
    public void LetGo()
    {
        if (!loaded && !playing)
        {
            return;
        }
        Position = Now;
        _ = Try(() => player?.Release());
        loaded = false;
        Playing = false;
        StopTicking();
    }

    /// <summary>Nothing plays or is loaded; the controls show the start.</summary>
    private void ForgetSong()
    {
        StopTicking();
        if (loaded || playing)
        {
            _ = Try(() => player?.Release());
        }
        loaded = false;
        Playing = false;
        atEnd = false;
        Song = null;
        clicks = null;
        OnScreen = false;
        Position = 0;
        Length = 0;
        Bars = [];
    }

    private void StartTicking()
    {
        StopTicking();
        var token = new object();
        tickToken = token;
        ticking = ticker(() =>
        {
            if (ReferenceEquals(tickToken, token))
            {
                Position = Now;
            }
        });
    }

    private void StopTicking()
    {
        tickToken = null;
        ticking?.Dispose();
        ticking = null;
    }

    /// <summary>The sounding bar's written number, set when it changes.</summary>
    private void Follow() => Marked = song is null ? null : Timeline.Written(bars, position);

    // the core

    private void Step(int count)
    {
        if (CanPlay && core is { } asked && song is { } wanted)
        {
            Ask(asked, wanted, at => Command.StepBy(at, count));
        }
    }

    /// <summary>Asks the core where to go from the position and goes there, unless the song changed
    /// meanwhile. The questions go out one after another, each from where the one before went, so
    /// two quick presses of Right go two bars on.</summary>
    private void Ask(ICore asked, string wanted, Func<double, Command> question)
    {
        _ = moves.Run(async () =>
        {
            var command = await OnWindow(() => wanted == song ? question(Now) : null).ConfigureAwait(false);
            if (command is null)
            {
                return;
            }
            if (await Request(asked, command, Seconds.From).ConfigureAwait(false) is { Value: { } seconds })
            {
                await OnWindow(() =>
                {
                    if (wanted == song)
                    {
                        Seek(seconds);
                    }
                }).ConfigureAwait(false);
            }
        });
    }

    /// <summary>Remembers the volumes given and plays at the gains the core answers. The commands go
    /// out one after another in the reader's order, so the core keeps the newest slider value; an
    /// answer that a newer change overtook is dropped.</summary>
    private Task ChangeVolumes(double? song, double? hits)
    {
        var mine = ++volumeRequest;
        return volumes.Run(async () =>
        {
            var (asked, wanted) = await OnWindow(() => (core, hear)).ConfigureAwait(false);
            if (asked is null)
            {
                return;
            }
            if (await Request(asked, Command.Volumes(wanted, song, hits), Gains.From).ConfigureAwait(false) is { } reply)
            {
                await OnWindow(() =>
                {
                    if (mine == volumeRequest && ReferenceEquals(asked, core))
                    {
                        gains = reply;
                        if (loaded)
                        {
                            _ = Try(() => player?.SetGains(reply));
                        }
                    }
                }).ConfigureAwait(false);
            }
        });
    }

    /// <summary>Sends <paramref name="command"/> and reads its reply; <c>null</c> when it was
    /// refused (the reader is told why) or the core is gone or answered something unreadable.</summary>
    private async Task<T?> Request<T>(ICore asked, Command command, Func<Reply, T> read)
        where T : class
    {
        try
        {
            return read(await asked.SendAsync(command).ConfigureAwait(false));
        }
        catch (CoreRefusedException refusal)
        {
            post(() => tell(new Notice(refusal.Error.Message, null)));
        }
        catch (CoreNotRunningException)
        {
            // the stopped page follows through the app's model
        }
        catch (UnreadableLineException)
        {
            // a reply without the fields this release reads: nothing changes
        }
        return null;
    }

    private void Failed(PlayerException failure) => tell(new Notice(failure.Message, null));

    /// <summary>Does <paramref name="call"/> on the player; false when it failed (the reader is told).</summary>
    private bool Try(Action call)
    {
        try
        {
            call();
            return true;
        }
        catch (PlayerException failure)
        {
            Failed(failure);
            return false;
        }
    }

    /// <summary>Runs <paramref name="work"/> on the window's thread and gives its result back.</summary>
    private Task<T> OnWindow<T>(Func<T> work)
    {
        var done = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        post(() =>
        {
            try
            {
                done.SetResult(work());
            }
            catch (Exception failure)
            {
                done.SetException(failure); // whoever waits sees it, and its `finally` runs
            }
        });
        return done.Task;
    }

    private async Task OnWindow(Action work) => await OnWindow(() =>
    {
        work();
        return true;
    }).ConfigureAwait(false);

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

    /// <summary>Runs jobs one after another, each after the one before has finished.</summary>
    internal sealed class Lane
    {
        private Task last = Task.CompletedTask;

        public Task Last => last;

        public Task Run(Func<Task> job)
        {
            var before = last;
            last = Task.Run(async () =>
            {
                try
                {
                    await before.ConfigureAwait(false);
                }
                catch (Exception)
                {
                    // the job before failed; its own caller sees that, this one still runs
                }
                await job().ConfigureAwait(false);
            });
            return last;
        }
    }
}
