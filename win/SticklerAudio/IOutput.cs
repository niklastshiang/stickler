namespace Stickler.Audio;

/// <summary>The sound device behind an interface (the app's is WASAPI; a fake in tests). It is
/// made for one run of playing and disposed when playing stops, so nothing holds the device
/// while the song is paused.</summary>
public interface IOutput : IDisposable
{
    /// <summary>It stopped by itself, on any thread: <c>null</c> when the source ran out and
    /// everything was played, else what went wrong with the device.</summary>
    event Action<Exception?>? Stopped;

    /// <summary>How far what is heard lags behind what was read from the source.</summary>
    TimeSpan Latency { get; }

    void Play();
}
