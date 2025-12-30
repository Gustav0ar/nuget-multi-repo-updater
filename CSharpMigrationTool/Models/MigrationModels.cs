using System.Text.Json.Serialization;

namespace CSharpMigrationTool;

public class MigrationRulesContainer
{
    [JsonPropertyName("rules")]
    public List<MigrationRule> Rules { get; set; } = new();
}

public class MigrationRule
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("target_nodes")]
    public List<TargetNode> TargetNodes { get; set; } = new();

    [JsonPropertyName("action")]
    public MigrationAction Action { get; set; } = new();
}

public class TargetNode
{
    [JsonPropertyName("type")]
    public string Type { get; set; } = string.Empty;

    [JsonPropertyName("method_name")]
    public string? MethodName { get; set; }

    [JsonPropertyName("class_name")]
    public string? ClassName { get; set; }

    [JsonPropertyName("identifier")]
    public string? Identifier { get; set; }

    [JsonPropertyName("containing_type")]
    public string? ContainingType { get; set; }

    [JsonPropertyName("containing_namespace")]
    public string? ContainingNamespace { get; set; }

    [JsonPropertyName("attributes")]
    public List<string>? Attributes { get; set; }

    [JsonPropertyName("parameters")]
    public List<ParameterInfo>? Parameters { get; set; }
}

public class ParameterInfo
{
    [JsonPropertyName("type")]
    public string Type { get; set; } = string.Empty;

    [JsonPropertyName("name")]
    public string? Name { get; set; }
}

public class MigrationAction
{
    [JsonPropertyName("type")]
    public string Type { get; set; } = string.Empty;

    [JsonPropertyName("strategy")]
    public string? Strategy { get; set; }

    [JsonPropertyName("replacement_method")]
    public string? ReplacementMethod { get; set; }

    [JsonPropertyName("replacement_code")]
    public string? ReplacementCode { get; set; }

    [JsonPropertyName("replacement_type")]
    public string? ReplacementType { get; set; }

    [JsonPropertyName("attribute_name")]
    public string? AttributeName { get; set; }

    [JsonPropertyName("preserve_parameters")]
    public bool? PreserveParameters { get; set; }

    [JsonPropertyName("preserve_variable_names")]
    public bool? PreserveVariableNames { get; set; }

    [JsonPropertyName("argument_name")]
    public string? ArgumentName { get; set; }
}

public class MigrationResult
{
    [JsonPropertyName("success")]
    public bool Success { get; set; } = true;

    [JsonPropertyName("modified_files")]
    public List<string> ModifiedFiles { get; set; } = new();

    [JsonPropertyName("applied_rules")]
    public List<string> AppliedRules { get; set; } = new();

    [JsonPropertyName("errors")]
    public List<string> Errors { get; set; } = new();

    [JsonPropertyName("summary")]
    public string Summary { get; set; } = string.Empty;

    public static MigrationResult CreateSuccess(List<string> modifiedFiles, List<string> appliedRules, string summary)
    {
        return new MigrationResult
        {
            Success = true,
            ModifiedFiles = modifiedFiles,
            AppliedRules = appliedRules,
            Summary = summary
        };
    }

    public static MigrationResult CreateFailed(string error)
    {
        return new MigrationResult
        {
            Success = false,
            Errors = new List<string> { error },
            Summary = "Migration failed"
        };
    }

    public void AddError(string error)
    {
        Errors.Add(error);
        Success = false;
    }

    public void AddAppliedRule(string ruleName)
    {
        if (!AppliedRules.Contains(ruleName))
        {
            AppliedRules.Add(ruleName);
        }
    }

    public void AddModifiedFile(string filePath)
    {
        if (!ModifiedFiles.Contains(filePath))
        {
            ModifiedFiles.Add(filePath);
        }
    }
}
