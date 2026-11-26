namespace Stickler.Core.Tests;

[TestClass]
public sealed class WindowSettingsTests
{
    private static readonly string Sep = Path.DirectorySeparatorChar.ToString();

    private static string Folder()
    {
        var folder = Path.Combine(Path.GetTempPath(), "stickler-window-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        return folder;
    }

    private static void Clean(string folder) => Directory.Delete(folder, recursive: true);

    [TestMethod]
    public void TheFileSitsInTheXdgConfigFolderWhenItIsSet()
    {
        var env = new Dictionary<string, string?>
        {
            ["XDG_CONFIG_HOME"] = "cfg",
            ["LOCALAPPDATA"] = "local",
        };
        Assert.AreEqual(Path.Combine("cfg", "stickler", "window.json"), WindowSettings.PathFor(env));
    }

    [TestMethod]
    public void TheFileSitsUnderLocalAppDataWithoutAnXdgFolder()
    {
        var env = new Dictionary<string, string?> { ["XDG_CONFIG_HOME"] = "", ["LOCALAPPDATA"] = "local" };
        Assert.AreEqual(Path.Combine("local", "Stickler", "config", "window.json"), WindowSettings.PathFor(env));
    }

    [TestMethod]
    public void TheFileFallsBackToTheHomesAppDataLocal()
    {
        var withProfile = new Dictionary<string, string?> { ["USERPROFILE"] = "up", ["HOME"] = "h" };
        Assert.AreEqual(
            Path.Combine("up", "AppData", "Local", "Stickler", "config", "window.json"),
            WindowSettings.PathFor(withProfile));
        var withHome = new Dictionary<string, string?> { ["HOME"] = "h", ["LOCALAPPDATA"] = null };
        Assert.AreEqual(
            Path.Combine("h", "AppData", "Local", "Stickler", "config", "window.json"),
            WindowSettings.PathFor(withHome));
    }

    [TestMethod]
    public void WithoutAnyVariableTheSystemsHomeIsUsed()
    {
        var path = WindowSettings.PathFor(new Dictionary<string, string?>());
        StringAssert.EndsWith(path, Sep + Path.Combine("AppData", "Local", "Stickler", "config", "window.json"));
    }

    [TestMethod]
    public void WhatWasSavedIsLoadedAgain()
    {
        var folder = Folder();
        try
        {
            var path = Path.Combine(folder, "window.json");
            Assert.IsTrue(new WindowSettings(true).Save(path));
            Assert.IsTrue(WindowSettings.Load(path).CorrectionsShown);
            Assert.IsTrue(new WindowSettings(false).Save(path));
            Assert.IsFalse(WindowSettings.Load(path).CorrectionsShown);
        }
        finally
        {
            Clean(folder);
        }
    }

    [TestMethod]
    public void AMissingFileGivesTheDefault()
    {
        var folder = Folder();
        try
        {
            Assert.AreEqual(new WindowSettings(false), WindowSettings.Load(Path.Combine(folder, "none.json")));
        }
        finally
        {
            Clean(folder);
        }
    }

    [TestMethod]
    public void AFolderWhereTheFileShouldBeGivesTheDefault()
    {
        var folder = Folder();
        try
        {
            Assert.AreEqual(new WindowSettings(false), WindowSettings.Load(folder));
        }
        finally
        {
            Clean(folder);
        }
    }

    [TestMethod]
    public void AnUnreadableFileGivesTheDefault()
    {
        foreach (var text in new[] { "", "{not json", "[true]", "{\"corrections_shown\": \"yes\"}", "{\"corrections_shown\": 1}", "{}" })
        {
            var folder = Folder();
            try
            {
                var path = Path.Combine(folder, "window.json");
                File.WriteAllText(path, text);
                Assert.IsFalse(WindowSettings.Load(path).CorrectionsShown, text);
            }
            finally
            {
                Clean(folder);
            }
        }
    }

    [TestMethod]
    public void UnknownFieldsAreIgnoredOnLoad()
    {
        var folder = Folder();
        try
        {
            var path = Path.Combine(folder, "window.json");
            File.WriteAllText(path, "{\"other\": [1], \"corrections_shown\": true}");
            Assert.IsTrue(WindowSettings.Load(path).CorrectionsShown);
        }
        finally
        {
            Clean(folder);
        }
    }

    [TestMethod]
    public void SaveCreatesTheFolderAndWritesTheField()
    {
        var folder = Folder();
        try
        {
            var path = Path.Combine(folder, "a", "b", "window.json");
            Assert.IsTrue(new WindowSettings(true).Save(path));
            StringAssert.Contains(File.ReadAllText(path), "\"corrections_shown\": true");
        }
        finally
        {
            Clean(folder);
        }
    }

    [TestMethod]
    public void SaveReplacesAnExistingFileAndLeavesNoTemporaryFile()
    {
        var folder = Folder();
        try
        {
            var path = Path.Combine(folder, "window.json");
            File.WriteAllText(path, "{\"corrections_shown\": false, \"x\": 1}");
            Assert.IsTrue(new WindowSettings(true).Save(path));
            Assert.IsTrue(WindowSettings.Load(path).CorrectionsShown);
            Assert.AreEqual(path, Directory.GetFiles(folder).Single());
        }
        finally
        {
            Clean(folder);
        }
    }

    [TestMethod]
    public void SaveToAnUnwritablePlaceReturnsFalse()
    {
        var folder = Folder();
        try
        {
            var blocker = Path.Combine(folder, "file");
            File.WriteAllText(blocker, "x");
            Assert.IsFalse(new WindowSettings(true).Save(Path.Combine(blocker, "window.json")));
            Assert.IsFalse(new WindowSettings(true).Save(folder));
            Assert.AreEqual(blocker, Directory.GetFiles(folder).Single());
        }
        finally
        {
            Clean(folder);
        }
    }
}
