using System.ComponentModel;
using System.Diagnostics;
using System.Text;

namespace Stickler.Core;

public enum CoreEndReason
{
    /// <summary>The process exited with <see cref="CoreEnd.Code"/> (0 after <c>quit</c>).</summary>
    Exited,

    /// <summary>Its <c>hello</c> named another protocol: app and core are from different releases.</summary>
    WrongProtocol,

    /// <summary>It could not be started at all (a part of the app is missing, a wrong checkout).</summary>
    NotStarted,
}

/// <summary>How the core ended: for the page "Stickler Stopped Unexpectedly".</summary>
public sealed record CoreEnd(CoreEndReason Reason, int Code, string Why, IReadOnlyList<string> Details)
{
    /// <summary>One line on how it ended, for "Technical Details" (not translated, as the rest there).</summary>
    public string Summary => Reason switch
    {
        CoreEndReason.Exited => $"The core exited with status {Code}.",
        CoreEndReason.WrongProtocol => $"The core speaks protocol {Code}; this app speaks {BridgeProtocol.Version}.",
        _ => $"The core could not be started: {Why}",
    };

    /// <summary>Whether the core never ran: the page then shows its details at once.</summary>
    public bool NeverStarted => Reason == CoreEndReason.NotStarted;

    public string TechnicalDetails => string.Join("\n", new[] { Summary }.Concat(Details));
}

/// <summary>The core is not running (not started yet, or ended before the reply came).</summary>
public sealed class CoreNotRunningException : Exception
{
    public CoreNotRunningException() : base("The core is not running.") { }

    public CoreNotRunningException(string message) : base(message) { }

    public CoreNotRunningException(string message, Exception inner) : base(message, inner) { }
}

/// <summary>The core answered a command with an error reply.</summary>
public sealed class CoreRefusedException : Exception
{
    public CoreRefusedException() : this(new BridgeError("internal", "")) { }

    public CoreRefusedException(string message) : this(new BridgeError("internal", message)) { }

    public CoreRefusedException(string message, Exception inner) : base(message, inner) =>
        Error = new BridgeError("internal", message);

    public CoreRefusedException(BridgeError error) : base(error.Message) => Error = error;

    public BridgeError Error { get; }
}

/// <summary>What the app needs of the core (<see cref="CoreClient"/>; a fake in tests).</summary>
public interface ICore
{
    /// <summary>Starts the core. <paramref name="onEvent"/> gets <c>hello</c> and every event in
    /// the core's order; <paramref name="onEnd"/> comes once, after the last event, also when
    /// the core cannot be started.</summary>
    void Start(Action<Incoming> onEvent, Action<CoreEnd> onEnd);

    /// <summary>Sends <paramref name="command"/> and waits for its reply. Throws
    /// <see cref="CoreRefusedException"/> for an error reply and <see cref="CoreNotRunningException"/>
    /// when the core is not there or ends first.</summary>
    Task<Reply> SendAsync(Command command, CancellationToken cancel = default);

    /// <summary>Ends the core politely within <paramref name="seconds"/>, then for good.</summary>
    Task QuitAsync(double seconds);
}

/// <summary>The core as a subprocess speaking JSON lines (<c>docs/bridge.md</c>). It reads the
/// core's stdout and stderr on tasks of its own, hands every event to <c>onEvent</c> in the
/// order the core sent them, answers each <see cref="SendAsync"/> with its reply, and calls
/// <c>onEnd</c> once when the core is gone, after its last event.</summary>
public sealed class CoreClient : ICore, IDisposable
{
    public const int DetailLines = 40;

    private static readonly UTF8Encoding Utf8 = new(encoderShouldEmitUTF8Identifier: false);

    private readonly Lock gate = new();
    private readonly SemaphoreSlim writing = new(1, 1);
    private readonly Dictionary<int, TaskCompletionSource<Reply>> waiting = [];
    private readonly Queue<string> stderrTail = new();
    private readonly Queue<string> unreadable = new();
    private Process? process;
    private int nextId = 1;
    private int openStreams;
    private int? exitCode;
    private int? refusedProtocol;
    private bool ended;
    private Action<Incoming> onEvent = _ => { };
    private Action<CoreEnd> onEnd = _ => { };

    /// <summary><paramref name="environment"/> is added to this process's own, without the
    /// variables that begin with one of <paramref name="drops"/>. A core whose
    /// <paramref name="needs"/> are not all there is not started.</summary>
    public CoreClient(
        string executable,
        IReadOnlyList<string> arguments,
        string? directory = null,
        IReadOnlyDictionary<string, string>? environment = null,
        IReadOnlyList<string>? needs = null,
        IReadOnlyList<string>? drops = null)
    {
        Executable = executable;
        Arguments = arguments;
        Directory = directory;
        Environment = environment ?? new Dictionary<string, string>();
        Needs = needs ?? [];
        Drops = drops ?? [];
    }

    public string Executable { get; }

    public IReadOnlyList<string> Arguments { get; }

    public string? Directory { get; }

    public IReadOnlyDictionary<string, string> Environment { get; }

    public IReadOnlyList<string> Needs { get; }

    public IReadOnlyList<string> Drops { get; }

    public bool IsRunning
    {
        get
        {
            lock (gate)
            {
                return process is { } running && !running.HasExited;
            }
        }
    }

    /// <summary>The core's process id, while it runs.</summary>
    public int? ProcessId
    {
        get
        {
            lock (gate)
            {
                return process is { } running && !running.HasExited ? running.Id : null;
            }
        }
    }

    /// <summary>What of <paramref name="needs"/> is not there.</summary>
    public static IReadOnlyList<string> Missing(IEnumerable<string> needs) =>
        needs.Where(need => !File.Exists(need) && !System.IO.Directory.Exists(need))
            .Select(need => $"missing: {need}")
            .ToList();

    public void Start(Action<Incoming> onEvent, Action<CoreEnd> onEnd)
    {
        ArgumentNullException.ThrowIfNull(onEvent);
        ArgumentNullException.ThrowIfNull(onEnd);
        var missing = Missing(Needs);
        if (missing.Count > 0)
        {
            onEnd(new CoreEnd(CoreEndReason.NotStarted, 0, "parts of it are missing", missing));
            return;
        }
        var start = new ProcessStartInfo(Executable)
        {
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
            StandardInputEncoding = Utf8,
            StandardOutputEncoding = Utf8,
            StandardErrorEncoding = Utf8,
        };
        if (Directory is not null)
        {
            start.WorkingDirectory = Directory;
        }
        foreach (var argument in Arguments)
        {
            start.ArgumentList.Add(argument);
        }
        foreach (var name in start.Environment.Keys.ToList())
        {
            if (Drops.Any(drop => name.StartsWith(drop, StringComparison.OrdinalIgnoreCase)))
            {
                start.Environment.Remove(name);
            }
        }
        foreach (var (name, value) in Environment)
        {
            start.Environment[name] = value;
        }
        var started = new Process { StartInfo = start, EnableRaisingEvents = true };
        lock (gate)
        {
            this.onEvent = onEvent;
            this.onEnd = onEnd;
            process = started;
            openStreams = 2;
        }
        try
        {
            started.Start();
        }
        catch (Exception error) when (error is Win32Exception or InvalidOperationException or IOException)
        {
            lock (gate)
            {
                process = null;
                openStreams = 0;
            }
            started.Dispose();
            onEnd(new CoreEnd(CoreEndReason.NotStarted, 0, error.Message, []));
            return;
        }
        started.StandardInput.AutoFlush = false;
        _ = Task.Run(() => ReadAsync(started.StandardOutput, Received));
        _ = Task.Run(() => ReadAsync(started.StandardError, KeepStderr));
        _ = Task.Run(async () =>
        {
            await started.WaitForExitAsync().ConfigureAwait(false);
            lock (gate)
            {
                exitCode = started.ExitCode;
            }
            EndIfDone();
        });
    }

    public async Task<Reply> SendAsync(Command command, CancellationToken cancel = default)
    {
        ArgumentNullException.ThrowIfNull(command);
        var answer = new TaskCompletionSource<Reply>(TaskCreationOptions.RunContinuationsAsynchronously);
        int id;
        StreamWriter input;
        lock (gate)
        {
            if (process is null || ended)
            {
                throw new CoreNotRunningException();
            }
            id = nextId++;
            waiting[id] = answer;
            input = process.StandardInput;
        }
        using var registration = cancel.Register(() =>
        {
            lock (gate)
            {
                waiting.Remove(id);
            }
            answer.TrySetCanceled(cancel);
        });
        // a cancelled wait (a quit's time limit) also ends a wait for the pipe or a blocked write;
        // the registration above has already let go of the reply
        await writing.WaitAsync(cancel).ConfigureAwait(false);
        try
        {
            // one writer at a time, and always "\n": the bridge reads lines (docs/bridge.md)
            await input.WriteAsync((command.Line(id) + "\n").AsMemory(), cancel).ConfigureAwait(false);
            await input.FlushAsync(cancel).ConfigureAwait(false);
        }
        catch (Exception error) when (error is IOException or ObjectDisposedException or InvalidOperationException)
        {
            lock (gate)
            {
                waiting.Remove(id);
            }
            answer.TrySetException(new CoreNotRunningException("The core stopped reading.", error));
        }
        finally
        {
            writing.Release();
        }
        return await answer.Task.ConfigureAwait(false);
    }

    /// <summary>Ends the core politely within <paramref name="seconds"/>: <c>quit</c>, then
    /// stdin closed; still running at the deadline, its whole process tree is ended (uv, the
    /// bridge and a model it runs).</summary>
    public async Task QuitAsync(double seconds)
    {
        var deadline = DateTime.UtcNow.AddSeconds(seconds);
        try
        {
            using var limit = new CancellationTokenSource(TimeSpan.FromSeconds(seconds));
            await SendAsync(Command.Quit, limit.Token).ConfigureAwait(false);
        }
        catch (Exception error) when (error is CoreNotRunningException or CoreRefusedException or OperationCanceledException)
        {
            // gone already, or not answering: ended below
        }
        Process? running;
        lock (gate)
        {
            running = process;
        }
        if (running is null)
        {
            return;
        }
        try
        {
            running.StandardInput.Close();
        }
        catch (Exception error) when (error is IOException or InvalidOperationException or ObjectDisposedException)
        {
            // its stdin is closed already
        }
        await WaitForExitAsync(running, deadline).ConfigureAwait(false);
        Kill(running);
        await WaitForExitAsync(running, DateTime.UtcNow.AddSeconds(2)).ConfigureAwait(false);
    }

    /// <summary>Ends the core and everything it started at once.</summary>
    public void Terminate()
    {
        Process? running;
        lock (gate)
        {
            running = process;
        }
        if (running is not null)
        {
            Kill(running);
        }
    }

    public void Dispose()
    {
        Terminate();
        writing.Dispose();
    }

    private static void Kill(Process running)
    {
        try
        {
            if (!running.HasExited)
            {
                running.Kill(entireProcessTree: true);
            }
        }
        catch (Exception error) when (error is InvalidOperationException or Win32Exception or NotSupportedException)
        {
            // it ended meanwhile
        }
    }

    private static async Task WaitForExitAsync(Process running, DateTime deadline)
    {
        var left = deadline - DateTime.UtcNow;
        if (left <= TimeSpan.Zero)
        {
            return;
        }
        using var limit = new CancellationTokenSource(left);
        try
        {
            await running.WaitForExitAsync(limit.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            // still running at the deadline
        }
    }

    private async Task ReadAsync(StreamReader reader, Action<string> line)
    {
        try
        {
            while (await reader.ReadLineAsync().ConfigureAwait(false) is { } next)
            {
                line(next);
            }
        }
        catch (Exception error) when (error is IOException or ObjectDisposedException)
        {
            // the pipe broke with the process
        }
        finally
        {
            // the end comes even when a line's handler threw
            lock (gate)
            {
                openStreams--;
            }
            EndIfDone();
        }
    }

    private void KeepStderr(string line)
    {
        lock (gate)
        {
            stderrTail.Enqueue(line);
            while (stderrTail.Count > DetailLines)
            {
                stderrTail.Dequeue();
            }
        }
    }

    private void Received(string line)
    {
        Incoming incoming;
        try
        {
            incoming = Incoming.Parse(line);
        }
        catch (UnreadableLineException)
        {
            lock (gate)
            {
                unreadable.Enqueue($"unreadable line from the core: {(line.Length > 200 ? line[..200] + "…" : line)}");
                while (unreadable.Count > 5)
                {
                    unreadable.Dequeue();
                }
            }
            return;
        }
        switch (incoming)
        {
            case ReplyLine { Reply: var reply }:
                TaskCompletionSource<Reply>? waiter = null;
                lock (gate)
                {
                    if (reply.Id is int id && waiting.Remove(id, out var found))
                    {
                        waiter = found;
                    }
                }
                if (reply.Error is { } error)
                {
                    waiter?.TrySetException(new CoreRefusedException(error));
                }
                else
                {
                    waiter?.TrySetResult(reply);
                }
                break;
            case HelloLine { Hello.Protocol: var spoken } when spoken != BridgeProtocol.Version:
                lock (gate)
                {
                    refusedProtocol = spoken;
                }
                Terminate();
                break;
            default:
                Action<Incoming> deliver;
                lock (gate)
                {
                    deliver = onEvent;
                }
                deliver(incoming);
                break;
        }
    }

    // the end: after the exit and both streams' last lines, once
    private void EndIfDone()
    {
        CoreEnd end;
        List<TaskCompletionSource<Reply>> left;
        Action<CoreEnd> notify;
        lock (gate)
        {
            if (ended || exitCode is not int code || openStreams > 0)
            {
                return;
            }
            ended = true;
            var details = stderrTail.Concat(unreadable).ToList();
            end = refusedProtocol is int spoken
                ? new CoreEnd(CoreEndReason.WrongProtocol, spoken, "", details)
                : new CoreEnd(CoreEndReason.Exited, code, "", details);
            left = [.. waiting.Values];
            waiting.Clear();
            notify = onEnd;
        }
        foreach (var waiter in left)
        {
            waiter.TrySetException(new CoreNotRunningException());
        }
        notify(end);
    }
}
