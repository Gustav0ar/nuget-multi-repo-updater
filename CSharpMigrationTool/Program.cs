using System.CommandLine;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace CSharpMigrationTool;

class Program
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true,
        WriteIndented = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.Never
    };

    static async Task<int> Main(string[] args)
    {
        var rootCommand = new RootCommand("C# Code Migration Tool using Roslyn");

        var rulesFileOption = new Option<FileInfo>(
            name: "--rules-file",
            description: "Path to the JSON file containing migration rules")
        {
            IsRequired = true
        };

        var targetFilesOption = new Option<List<FileInfo>>(
            name: "--target-file",
            description: "C# file to process (can be specified multiple times)")
        {
            IsRequired = true,
            AllowMultipleArgumentsPerToken = true
        };

        var workingDirectoryOption = new Option<DirectoryInfo>(
            name: "--working-directory",
            description: "Working directory for file operations");

        rootCommand.AddOption(rulesFileOption);
        rootCommand.AddOption(targetFilesOption);
        rootCommand.AddOption(workingDirectoryOption);

        rootCommand.SetHandler(async (FileInfo rulesFile, List<FileInfo> targetFiles, DirectoryInfo? workingDir) =>
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
                var rulesData = JsonSerializer.Deserialize<MigrationRulesContainer>(rulesJson, JsonOptions);

                if (rulesData?.Rules == null)
                {
                    await WriteResultAsync(MigrationResult.CreateFailed("No migration rules found in rules file"));
                    Environment.Exit(1);
                    return;
                }

                // Convert FileInfo list to string paths and filter existing files
                var files = targetFiles
                             .Where(f => f.Exists)
                             .Select(f => f.FullName)
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
        var json = JsonSerializer.Serialize(result, JsonOptions);
        await Console.Out.WriteAsync(json);
    }
}
