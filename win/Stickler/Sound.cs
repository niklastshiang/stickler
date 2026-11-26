using NAudio.Wave;
using Stickler.Audio;

namespace Stickler;

/// <summary>Windows' side of the player (SPEC.md, module <c>win-playback</c>, scope 3): the
/// sound device and Media Foundation's reader behind SticklerAudio's interfaces. What is decided
/// (when a device is opened, what a failure means) is in <see cref="Player"/>, tested on Linux.</summary>
internal static class Sound
{
    private static readonly string[] Managed = [".wav", ".aif", ".aiff", ".aifc"];

    /// <summary>The player the app's model drives; <paramref name="cannotPlay"/> words a failure.</summary>
    public static Player Player(Func<Exception, string> cannotPlay) =>
        new(Song, WaveStreamSamples.Open, source => new WasapiOutput(source), cannotPlay);

    // WAV and AIFF by NAudio's own readers (Media Foundation has none for AIFF); everything else
    // by Media Foundation, which throws for what Windows cannot decode (Ogg, Opus).
    private static WaveStreamSamples Song(string path) =>
        Managed.Contains(Path.GetExtension(path), StringComparer.OrdinalIgnoreCase)
            ? WaveStreamSamples.Open(path)
            : new WaveStreamSamples(new MediaFoundationReader(path, new MediaFoundationReader.MediaFoundationReaderSettings
            {
                RequestFloatOutput = true,
                RepositionInRead = true, // a seek comes from the window's thread, the reading from the device's
            }));
}

/// <summary>WASAPI in shared mode, following Windows' default output device.</summary>
internal sealed class WasapiOutput : IOutput
{
    private readonly WasapiPlayer player;

    public WasapiOutput(ISampleProvider source)
    {
        // Following the default device is activated asynchronously; off the window's thread, so
        // waiting here cannot wait for itself.
        player = Task.Run(() => new WasapiPlayerBuilder().WithDefaultDeviceStreamRouting().BuildAsync()).GetAwaiter().GetResult();
        try
        {
            player.PlaybackStopped += (_, stop) => Stopped?.Invoke(stop.Exception);
            player.Init(source.ToWaveProvider());
        }
        catch
        {
            player.Dispose();
            throw;
        }
    }

    public event Action<Exception?>? Stopped;

    public TimeSpan Latency => TimeSpan.FromMilliseconds(player.LatencyMilliseconds);

    public void Play() => player.Play();

    public void Dispose() => player.Dispose();
}
