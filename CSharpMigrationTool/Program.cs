using System.CommandLine;
using Newtonsoft.Json;

namespace CSharpMigrationTool;

class Program
{
    static async Task<int> Main(string[] args)
    {
        var rootCommand = new RootCommand("C# Code Migration Tool using Roslyn");

        var rulesFileOption = new Option<FileInfo>(
            name: "--rules-file",
            description: "Path to the JSON file containing migration rules")
        {
            IsRequired = true
        };

        var targetFilesOption = new Option<string>(
            name: "--target-files",
            description: "Comma-separated list of C# files to process")
        {
            IsRequired = true
        };

        var workingDirectoryOption = new Option<DirectoryInfo>(
            name: "--working-directory",
            description: "Working directory for file operations");

        rootCommand.AddOption(rulesFileOption);
        rootCommand.AddOption(targetFilesOption);
        rootCommand.AddOption(workingDirectoryOption);

        rootCommand.SetHandler(async (FileInfo rulesFile, string targetFiles, DirectoryInfo? workingDir) =>
        {
            try
            {
                // Change to working directory if specified
                if (workingDir != null && workingDir.Exists)
                {
                    Environment.CurrentDirectory = workingDir.FullName;
                }

                // Load migration rules
                var rulesJson = await File.ReadAllTextAsync(rulesFile.FullName);
                var rulesData = JsonConvert.DeserializeObject<MigrationRulesContainer>(rulesJson);

                if (rulesData?.Rules == null)
                {
                    await WriteResultAsync(MigrationResult.CreateFailed("No migration rules found in rules file"));
                    Environment.Exit(1);
                    return;
                }

                // Parse target files
                var files = targetFiles.Split(',', StringSplitOptions.RemoveEmptyEntries)
                                     .Select(f => f.Trim())
                                     .Where(f => File.Exists(f))
                                     .ToList();

                if (!files.Any())
                {
                    await WriteResultAsync(MigrationResult.CreateSuccess(
                        new List<string>(), 
                        new List<string>(), 
                        "No valid target files found"));
                    Environment.Exit(0);
                    return;
                }

                // Execute migrations
                var migrationEngine = new MigrationEngine();
                var result = await migrationEngine.ExecuteMigrationsAsync(files, rulesData.Rules);

                await WriteResultAsync(result);
                Environment.Exit(result.Success ? 0 : 1);
            }
            catch (Exception ex)
            {
                await WriteResultAsync(MigrationResult.CreateFailed($"Unexpected error: {ex.Message}"));
                Environment.Exit(1);
            }
        }, rulesFileOption, targetFilesOption, workingDirectoryOption);

        return await rootCommand.InvokeAsync(args);
    }

    private static async Task WriteResultAsync(MigrationResult result)
    {
        var json = JsonConvert.SerializeObject(result, Formatting.Indented);
        await Console.Out.WriteAsync(json);
    }
}
