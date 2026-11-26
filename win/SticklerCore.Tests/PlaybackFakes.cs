using System.Text.Json;

namespace Stickler.Core.Tests;

/// <summary>A player that records what it is told; the test moves its position and pauses it.</summary>
internal sealed class FakePlayer : IPlaying
{
    private readonly Lock gate = new();
    private readonly List<(string Song, string? Clicks)> loads = [];
    private readonly List<double> seeks = [];
    private readonly List<Gains> gains = [];
    private HashSet<string> unreadable = [];
    private PlayerException? loadFailure;
    private PlayerException? playFailure;
    private bool endsAtOnce;
    private bool isPlaying;
    private double position;
    private int releases;

    public event Action<PlayerPause>? Paused;

    public IReadOnlyList<(string Song, string? Clicks)> Loads => Snapshot(loads);

    public IReadOnlyList<double> Seeks => Snapshot(seeks);

    public IReadOnlyList<Gains> GainsSet => Snapshot(gains);

    public int Releases => Locked(() => releases);

    /// <summary>Whether it was told to play and not to pause since.</summary>
    public bool IsPlaying => Locked(() => isPlaying);

    /// <summary>Plays from the end: it tells it ended inside <see cref="Play"/>, as an engine can.</summary>
    public bool EndsAtOnce
    {
        get => Locked(() => endsAtOnce);
        set => Locked(() =>
        {
            endsAtOnce = value;
        });
    }

    public double Position
    {
        get => Locked(() => position);
        set => Locked(() =>
        {
            position = value;
        });
    }

    public void Unreadable(params string[] songs) => Locked(() =>
    {
        unreadable = [.. songs];
    });

    public void FailToLoad(PlayerException? failure) => Locked(() =>
    {
        loadFailure = failure;
    });

    public void FailToPlay(PlayerException? failure) => Locked(() =>
    {
        playFailure = failure;
    });

    public void Load(string song, string? clicks)
    {
        lock (gate)
        {
            if (unreadable.Contains(song))
            {
                throw new PlayerUnreadableException($"Cannot read {Path.GetFileName(song)}.");
            }
            if (loadFailure is { } failure)
            {
                throw failure;
            }
            loads.Add((song, clicks));
            position = 0;
        }
    }

    public void Play()
    {
        lock (gate)
        {
            if (playFailure is { } failure)
            {
                throw failure;
            }
            if (endsAtOnce)
            {
                Paused?.Invoke(PlayerPause.Ended);
                return;
            }
            isPlaying = true;
        }
    }

    public void Pause() => Locked(() =>
    {
        isPlaying = false;
    });

    public void Seek(double seconds) => Locked(() =>
    {
        seeks.Add(seconds);
        position = seconds;
    });

    public void SetGains(Gains next) => Locked(() => gains.Add(next));

    public void Release() => Locked(() =>
    {
        releases++;
        isPlaying = false;
    });

    /// <summary>The player pauses by itself.</summary>
    public void Pauses(PlayerPause why)
    {
        Locked(() =>
        {
            isPlaying = false;
        });
        Paused?.Invoke(why);
    }

    private List<T> Snapshot<T>(List<T> source)
    {
        lock (gate)
        {
            return [.. source];
        }
    }

    private T Locked<T>(Func<T> read)
    {
        lock (gate)
        {
            return read();
        }
    }

    private void Locked(Action change)
    {
        lock (gate)
        {
            change();
        }
    }
}

/// <summary>A core that records the commands and answers as told, at once or after a delay;
/// the test sends its events.</summary>
internal sealed class PlaybackCore : ICore
{
    private readonly Lock gate = new();
    private readonly List<Command> commands = [];
    private readonly Dictionary<string, string> answers = [];
    private readonly Dictionary<string, List<(string Fields, TimeSpan Delay)>> queued = [];
    private Action<Incoming> onEvent = _ => { };
    private Action<CoreEnd> onEnd = _ => { };

    /// <summary>Every command sent, as its line.</summary>
    public IReadOnlyList<string> All
    {
        get
        {
            lock (gate)
            {
                return [.. commands.Select(c => c.Line(0))];
            }
        }
    }

    /// <summary>The commands without the sheet's and the playback's <c>settings</c> at start.</summary>
    public IReadOnlyList<string> Actions => [.. All.Where(line => Name(line) != "settings")];

    /// <summary>The lines of the commands named <paramref name="name"/>, oldest first.</summary>
    public IReadOnlyList<string> Asked(string name) => [.. All.Where(line => Name(line) == name)];

    /// <summary>The reply's fields after <c>"id": 1, </c> for <paramref name="command"/>.</summary>
    public void Answer(string command, string fields)
    {
        lock (gate)
        {
            answers[command] = fields;
        }
    }

    /// <summary>The next <paramref name="command"/> gets <paramref name="fields"/> after
    /// <paramref name="delay"/>; later ones get <see cref="Answer"/>'s again.</summary>
    public void Queue(string command, string fields, TimeSpan delay = default)
    {
        lock (gate)
        {
            if (!queued.TryGetValue(command, out var waiting))
            {
                queued[command] = waiting = [];
            }
            waiting.Add((fields, delay));
        }
    }

    public void Start(Action<Incoming> onEvent, Action<CoreEnd> onEnd)
    {
        this.onEvent = onEvent;
        this.onEnd = onEnd;
    }

    public async Task<Reply> SendAsync(Command command, CancellationToken cancel = default)
    {
        string fields;
        var delay = TimeSpan.Zero;
        lock (gate)
        {
            commands.Add(command);
            if (queued.TryGetValue(command.Name, out var waiting) && waiting.Count > 0)
            {
                (fields, delay) = waiting[0];
                waiting.RemoveAt(0);
            }
            else
            {
                fields = answers.GetValueOrDefault(command.Name, "\"ok\": true");
            }
        }
        if (delay > TimeSpan.Zero)
        {
            await Task.Delay(delay, cancel).ConfigureAwait(false);
        }
        if (fields == "not running")
        {
            throw new CoreNotRunningException();
        }
        var reply = Reply.Parse($"{{\"id\": 1, {fields}}}");
        return reply.Error is { } error ? throw new CoreRefusedException(error) : reply;
    }

    public Task QuitAsync(double seconds) => Task.CompletedTask;

    public void Emit(string line) => onEvent(Incoming.Parse(line));

    public void Stop(CoreEnd how) => onEnd(how);

    private static string Name(string line) => JsonElement.Parse(line).GetProperty("cmd").GetString()!;
}

/// <summary>The window's thread: work posted to it runs one piece at a time, as the dispatcher
/// queue does. A test calls the model through <see cref="Run"/>.</summary>
internal sealed class Window
{
    private readonly Lock gate = new();

    public void Post(Action work)
    {
        lock (gate)
        {
            work();
        }
    }

    public void Run(Action work) => Post(work);

    public T Read<T>(Func<T> read)
    {
        lock (gate)
        {
            return read();
        }
    }
}

/// <summary>A ticker the test fires by hand; it keeps every callback it was given, so a tick after
/// the model stopped listening can be fired too.</summary>
internal sealed class ManualTicker
{
    private readonly List<(Action Tick, Handle Handle)> started = [];

    public int Started => started.Count;

    public int Live => started.Count(s => !s.Handle.Disposed);

    public IDisposable Start(Action tick)
    {
        var handle = new Handle();
        started.Add((tick, handle));
        return handle;
    }

    /// <summary>Fires the newest tick, also when it was stopped.</summary>
    public void Fire() => started[^1].Tick();

    private sealed class Handle : IDisposable
    {
        public bool Disposed { get; private set; }

        public void Dispose() => Disposed = true;
    }
}

/// <summary>An <see cref="AppModel"/> with fake cores and a fake player.</summary>
internal sealed class PlaybackHarness
{
    public const string GainsReply = "\"ok\": true, \"song\": 0.7, \"hits\": 1.0";
    public const string SettingsReply =
        "\"ok\": true, \"appearance\": \"system\", \"zoom\": 1.0, \"song_volume\": 0.4, \"hits_volume\": 0.9, \"setup_agreed\": true, \"percent\": \"100%\"";
    public const string EmptyState = "{\"kind\": \"empty\", \"can_open\": true}";

    private readonly Lock gate = new();
    private readonly List<PlaybackCore> cores = [];
    private readonly Dictionary<string, string> preset = [];
    private readonly Dictionary<string, (string Fields, TimeSpan Delay)> late = [];

    public PlaybackHarness(IPlaying? player, Ticker? ticker = null)
    {
        Window = new Window();
        Model = new AppModel(["en"], _ =>
        {
            var core = new PlaybackCore();
            lock (gate)
            {
                foreach (var (command, fields) in preset)
                {
                    core.Answer(command, fields);
                }
                foreach (var (command, (fields, delay)) in late)
                {
                    core.Queue(command, fields, delay);
                    core.Queue(command, fields, delay); // the sheet asks for its note size too
                }
                cores.Add(core);
            }
            return core;
        }, Window.Post, TimeSpan.FromMilliseconds(300), player, ticker ?? PlaybackModel.Every(TimeSpan.FromMilliseconds(5), Window.Post));
    }

    public Window Window { get; }

    public AppModel Model { get; }

    public PlaybackModel Playback => Model.Playback;

    public PlaybackCore Core
    {
        get
        {
            lock (gate)
            {
                return cores[^1];
            }
        }
    }

    /// <summary>A player with the gains the core answers, as the tests of playing start.</summary>
    public static PlaybackHarness Playing(FakePlayer player, Ticker? ticker = null)
    {
        var harness = new PlaybackHarness(player, ticker);
        harness.Preset("volumes", GainsReply);
        harness.Window.Run(harness.Model.Launch);
        return harness;
    }

    /// <summary>Every core made from now on answers <paramref name="command"/> with <paramref name="fields"/>.</summary>
    public void Preset(string command, string fields)
    {
        lock (gate)
        {
            preset[command] = fields;
        }
    }

    /// <summary>Every core made from now on answers its first <paramref name="command"/> late.</summary>
    public void Preset(string command, string fields, TimeSpan delay)
    {
        lock (gate)
        {
            late[command] = (fields, delay);
        }
    }

    public void Ui(Action work) => Window.Run(work);

    public T Read<T>(Func<T> read) => Window.Read(read);

    /// <summary>Waits until <paramref name="condition"/> holds (read on the window's thread).</summary>
    public Task<bool> Settled(Func<bool> condition) => Recorder.Eventually(() => Window.Read(condition), 10);

    public static string Refusal(string message) =>
        $"\"ok\": false, \"error\": {{\"code\": \"not_now\", \"message\": \"{message}\"}}";

    public static string ExportingEvent(int seq) =>
        $"{{\"event\": \"state\", \"seq\": {seq}, \"state\": {{\"kind\": \"exporting\", \"song\": \"/m/e.flac\", \"title\": \"Eye of the Tiger\", \"subtitle\": \"Survivor\", \"dest\": \"/d/e.pdf\", \"steps\": []}}}}";

    public static string EmptyEvent(int seq) => $"{{\"event\": \"state\", \"seq\": {seq}, \"state\": {EmptyState}}}";

    /// <summary>A result whose song plays: the bars of <see cref="TimelineTests"/>, 12 s, clicks unless <paramref name="clicks"/> is null.</summary>
    public static string PlayingResult(
        int seq, string song = "/m/e.flac", string? clicks = "/c/e.wav", IReadOnlyList<SongBar>? bars = null)
    {
        var written = string.Join(", ", (bars ?? TimelineTests.SongBars).Select(bar =>
            $"{{\"start\": {bar.Start.ToString("R", System.Globalization.CultureInfo.InvariantCulture)}, \"end\": {bar.End.ToString("R", System.Globalization.CultureInfo.InvariantCulture)}, \"bar\": {bar.Bar}, \"label\": \"{bar.Label}\"}}"));
        var named = clicks is null ? "null" : $"\"{clicks}\"";
        return $"{{\"event\": \"state\", \"seq\": {seq}, \"state\": {{\"kind\": \"result\", \"song\": \"{song}\", \"title\": \"E\", \"subtitle\": \"S\", \"artist\": \"\", "
            + "\"seconds\": 12.0, \"tempo\": 109, \"meter\": [4, 4], \"musicxml\": \"/c/e.musicxml\", "
            + $"\"clicks\": {named}, \"bars\": [{written}], \"can_open\": true, \"can_close\": true, \"can_export\": true}}}}";
    }

    /// <summary>The lines of the <c>volumes</c> commands sent so far.</summary>
    public IReadOnlyList<string> VolumesAsked() => Core.Asked("volumes");

    /// <summary>The lines of the commands named <paramref name="name"/> that are sent so far, as a count.</summary>
    public int Count(string name) => Core.Asked(name).Count;
}
