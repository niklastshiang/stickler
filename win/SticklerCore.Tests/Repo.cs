using System.Diagnostics;
using System.Text.Json;

namespace Stickler.Core.Tests;

/// <summary>The repository, <c>uv</c>, and small fake cores written in Python, for the tests
/// that run real processes.</summary>
internal static class Repo
{
    public static string Root { get; } = Find();

    public static bool Windows { get; } = OperatingSystem.IsWindows();

    public static IReadOnlyDictionary<string, string?> Environment { get; } =
        System.Environment.GetEnvironmentVariables()
            .Cast<System.Collections.DictionaryEntry>()
            .ToDictionary(e => (string)e.Key, e => (string?)e.Value, StringComparer.OrdinalIgnoreCase);

    /// <summary><c>uv</c>: needed for these tests (CONSTRAINTS.md, "C# tests").</summary>
    public static string Uv { get; } =
        CoreLaunch.FindUv(Environment, Windows) ?? throw new InvalidOperationException("uv is needed for these tests");

    /// <summary>A fake core: Python running <paramref name="code"/> (stdout and stdin as bytes,
    /// so it writes "\n" on Windows too, as the bridge does).</summary>
    public static CoreClient FakeCore(string code, IReadOnlyList<string>? needs = null) =>
        new(Uv, ["run", "--no-project", "python", "-u", "-c", Prelude + code], Path.GetTempPath(), needs: needs);

    private const string Prelude =
        "import sys, json, time\n"
        + "def say(obj):\n"
        + "    sys.stdout.buffer.write((json.dumps(obj) + '\\n').encode()); sys.stdout.buffer.flush()\n"
        + "def lines():\n"
        + "    for raw in sys.stdin.buffer:\n"
        + "        yield raw\n";

    public static string Hello(int protocol = 1) =>
        $"say({{'event': 'hello', 'protocol': {protocol}, 'version': '11', 'language': 'en'}})\n";

    /// <summary>The stand-in models of <c>scripts/bridge_stand_ins.py</c>, set up once.</summary>
    public static Lazy<(string Models, string Song)> StandIns { get; } = new(() =>
    {
        var folder = Path.Combine(Path.GetTempPath(), $"stickler-stand-ins-{Guid.NewGuid():N}");
        var start = new ProcessStartInfo(Uv)
        {
            WorkingDirectory = Root,
            RedirectStandardOutput = true,
            UseShellExecute = false,
        };
        foreach (var argument in new[] { "run", "python", "scripts/bridge_stand_ins.py", folder })
        {
            start.ArgumentList.Add(argument);
        }
        start.Environment["UV_SYSTEM_CERTS"] = "1";
        using var process = Process.Start(start)!;
        var line = process.StandardOutput.ReadToEnd();
        process.WaitForExit();
        using var parsed = JsonDocument.Parse(line);
        return (parsed.RootElement.GetProperty("models").GetString()!, parsed.RootElement.GetProperty("song").GetString()!);
    });

    /// <summary>The real bridge with the stand-ins, its files in a folder of its own.</summary>
    public static CoreClient Bridge()
    {
        var (models, _) = StandIns.Value;
        var home = Path.Combine(Path.GetTempPath(), $"stickler-home-{Guid.NewGuid():N}");
        return new CoreClient(
            Uv,
            ["run", "python", "-m", "stickler_app.bridge"],
            Root,
            new Dictionary<string, string>
            {
                ["STICKLER_ADAPTERS"] = models,
                ["STICKLER_RESULTS_CACHE"] = Path.Combine(home, "results"),
                ["XDG_DATA_HOME"] = Path.Combine(home, "data"),
                ["XDG_CONFIG_HOME"] = Path.Combine(home, "config"),
                ["XDG_CACHE_HOME"] = Path.Combine(home, "cache"),
                ["LANGUAGE"] = "en",
                ["UV_SYSTEM_CERTS"] = "1",
            });
    }

    private static string Find()
    {
        for (var folder = new DirectoryInfo(AppContext.BaseDirectory); folder is not null; folder = folder.Parent)
        {
            if (File.Exists(Path.Combine(folder.FullName, "docs", "bridge.md")))
            {
                return folder.FullName;
            }
        }
        throw new InvalidOperationException("the tests run inside the repository");
    }
}

/// <summary>Collects what a client reports, from its tasks.</summary>
internal sealed class Recorder
{
    private readonly Lock gate = new();
    private readonly List<Incoming> incoming = [];
    private CoreEnd? end;

    public IReadOnlyList<Incoming> Events
    {
        get
        {
            lock (gate)
            {
                return [.. incoming];
            }
        }
    }

    public CoreEnd? Ended
    {
        get
        {
            lock (gate)
            {
                return end;
            }
        }
    }

    public void Start(ICore core) => core.Start(
        line =>
        {
            lock (gate)
            {
                incoming.Add(line);
            }
        },
        how =>
        {
            lock (gate)
            {
                end = how;
            }
        });

    public IEnumerable<AppState> States() => Events.OfType<StateEvent>().Select(e => e.State);

    /// <summary>Waits until <paramref name="condition"/> holds, at most <paramref name="seconds"/>.</summary>
    public static async Task<bool> Eventually(Func<bool> condition, double seconds = 60)
    {
        var deadline = DateTime.UtcNow.AddSeconds(seconds);
        while (DateTime.UtcNow < deadline)
        {
            if (condition())
            {
                return true;
            }
            await Task.Delay(20);
        }
        return condition();
    }
}
