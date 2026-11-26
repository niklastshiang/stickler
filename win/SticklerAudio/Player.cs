using NAudio.Wave;
using Stickler.Core;

namespace Stickler.Audio;

/// <summary>The app's player (SPEC.md, module <c>win-playback</c>, scope 3): the song and the
/// clicks through one <see cref="Mix"/> into one <see cref="IOutput"/>. Its methods are called on
/// the window's thread; <see cref="Paused"/> comes from the device's.</summary>
public sealed class Player : IPlaying, IDisposable
{
    private readonly object gate = new();
    private readonly Func<string, ISeekableSamples> openSong;
    private readonly Func<string, ISeekableSamples> openClicks;
    private readonly Func<ISampleProvider, IOutput> makeOutput;
    private readonly Func<Exception, string> cannotPlay;
    private Mix? mix;
    private IOutput? output; // only while playing
    private double floor; // where this run of playing began: nothing earlier was heard
    private bool stopped; // the device stopped by itself and waits to be disposed
    private bool finished; // the run played to the song's end
    private float songGain = 1;
    private float hitsGain = 1;

    /// <summary><paramref name="openSong"/> reads a song's file and throws when the system cannot
    /// (the core then decodes a copy); <paramref name="openClicks"/> reads the clicks' WAV;
    /// <paramref name="makeOutput"/> opens the sound device for a source;
    /// <paramref name="cannotPlay"/> words a failure for the reader.</summary>
    public Player(
        Func<string, ISeekableSamples> openSong,
        Func<string, ISeekableSamples> openClicks,
        Func<ISampleProvider, IOutput> makeOutput,
        Func<Exception, string> cannotPlay)
    {
        this.openSong = openSong;
        this.openClicks = openClicks;
        this.makeOutput = makeOutput;
        this.cannotPlay = cannotPlay;
    }

    public event Action<PlayerPause>? Paused;

    /// <summary>What is heard now: what the device read, less what it has not played yet.</summary>
    public double Position
    {
        get
        {
            lock (gate)
            {
                if (mix is null)
                {
                    return 0;
                }

                if (finished)
                {
                    return mix.Length;
                }

                double behind = output?.Latency.TotalSeconds ?? 0;
                return Math.Max(floor, mix.Position - behind);
            }
        }
    }

    public void Load(string song, string? clicks)
    {
        Release();
        ISeekableSamples music;
        try
        {
            music = openSong(song);
        }
        catch (Exception unreadable)
        {
            // Whatever the reader says (an unknown format, a missing codec): the core's copy is tried.
            throw new PlayerUnreadableException(cannotPlay(unreadable));
        }

        ISeekableSamples? hits = null;
        try
        {
            hits = clicks is not null && File.Exists(clicks) ? openClicks(clicks) : null;
            Mix next = new(music, hits);
            next.SetGains(songGain, hitsGain);
            lock (gate)
            {
                mix = next;
                floor = 0;
                finished = false;
            }
        }
        catch (Exception broken)
        {
            music.Dispose();
            hits?.Dispose();
            throw new PlayerFailedException(cannotPlay(broken));
        }
    }

    public void Play()
    {
        Mix? source;
        double? heard = null;
        lock (gate)
        {
            source = mix;
            if (source is null || (output is not null && !stopped))
            {
                return;
            }

            if (output is not null && !finished)
            {
                heard = Position; // interrupted: the device had read ahead of what was heard
            }
        }

        Close(); // a device that stopped by itself
        if (heard is { } back)
        {
            MoveTo(back);
        }

        lock (gate)
        {
            floor = source.Position;
            finished = false;
        }

        IOutput device;
        try
        {
            device = makeOutput(source);
        }
        catch (Exception noDevice)
        {
            throw new PlayerFailedException(cannotPlay(noDevice));
        }

        device.Stopped += why => StoppedByItself(device, why);
        lock (gate)
        {
            output = device;
        }

        try
        {
            device.Play();
        }
        catch (Exception refused)
        {
            Close();
            throw new PlayerFailedException(cannotPlay(refused));
        }
    }

    /// <summary>Stops the device and goes back to what was heard last, so playing goes on from
    /// there and not from what the device had read ahead.</summary>
    public void Pause()
    {
        double heard = Position;
        Close();
        MoveTo(heard);
    }

    /// <summary>While playing, the device is opened anew: what it had read ahead at the old place
    /// is not played after the jump.</summary>
    public void Seek(double seconds)
    {
        bool playing = Close();
        MoveTo(seconds);
        if (playing)
        {
            Play();
        }
    }

    public void SetGains(Gains gains)
    {
        songGain = (float)gains.Song;
        hitsGain = (float)gains.Hits;
        mix?.SetGains(songGain, hitsGain);
    }

    public void Release()
    {
        Close();
        Mix? old;
        lock (gate)
        {
            old = mix;
            mix = null;
            floor = 0;
            finished = false;
        }

        old?.Dispose();
    }

    public void Dispose() => Release();

    private void MoveTo(double seconds)
    {
        if (mix is not { } source)
        {
            return;
        }

        source.Seek(seconds);
        lock (gate)
        {
            floor = source.Position;
            finished = false;
        }
    }

    /// <summary>Lets go of the device; true when it was still playing (not stopped by itself).</summary>
    private bool Close()
    {
        IOutput? device;
        bool playing;
        lock (gate)
        {
            device = output;
            output = null;
            playing = device is not null && !stopped;
            stopped = false;
        }

        device?.Dispose();
        return playing;
    }

    /// <summary>The device's own stop, on its thread. A device this player closed itself says
    /// nothing; the one playing now tells the model, and is disposed with the next call from the
    /// window's thread (disposing it here would wait for the very thread that calls).</summary>
    private void StoppedByItself(IOutput device, Exception? why)
    {
        lock (gate)
        {
            if (!ReferenceEquals(device, output))
            {
                return;
            }

            stopped = true;
            finished = why is null;
        }

        Paused?.Invoke(why is null ? PlayerPause.Ended : PlayerPause.Interrupted);
    }
}
