# How to Use NuGet Migration Examples

## Quick Start

1. **Choose the right example** for your migration scenario
2. **Copy the migration rules** from the example's `migration-rules.json`
3. **Adapt the rules** to your specific needs
4. **Test on a small subset** of files first
5. **Run the migration tool** on your entire codebase

## Example Commands

### Using the Migration Tool

```bash
# Navigate to your project directory
cd /path/to/your/project

# Run migration on a single file (for testing)
dotnet run --project /path/to/migration-tool \
  --rules-file examples/nuget-migrations/remove-obsolete-methods/migration-rules.json \
  --target-files src/Services/ApiService.cs \
  --working-directory .

# Run migration on multiple files
dotnet run --project /path/to/migration-tool \
  --rules-file examples/nuget-migrations/complex-scenarios/combined-migration-rules.json \
  --target-files "src/**/*.cs" \
  --working-directory .

# Run migration on entire project
find src -name "*.cs" | xargs -I {} dotnet run --project /path/to/migration-tool \
  --rules-file migration-rules.json \
  --target-files {} \
  --working-directory .
```

### Integration with CI/CD

```yaml
# Example GitHub Actions workflow
name: NuGet Migration
on:
  workflow_dispatch:
    inputs:
      migration_type:
        description: 'Type of migration to run'
        required: true
        default: 'remove-obsolete-methods'
        type: choice
        options:
          - remove-obsolete-methods
          - method-renames
          - type-replacements
          - complex-scenarios

jobs:
  migrate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup .NET
        uses: actions/setup-dotnet@v3
        with:
          dotnet-version: '8.0.x'

      - name: Run Migration
        run: |
          dotnet run --project tools/migration-tool \
            --rules-file examples/nuget-migrations/${{ github.event.inputs.migration_type }}/migration-rules.json \
            --target-files "src/**/*.cs" \
            --working-directory .

      - name: Create Pull Request
        uses: peter-evans/create-pull-request@v5
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          commit-message: 'Apply ${{ github.event.inputs.migration_type }} migration'
          title: 'Auto-migration: ${{ github.event.inputs.migration_type }}'
          body: |
            Automated migration applied using migration rules.

            **Migration Type:** ${{ github.event.inputs.migration_type }}
            **Files Changed:** See file diff below

            Please review changes carefully before merging.
```

## Best Practices

### 1. Always Test First

```bash
# Create a backup
git checkout -b migration-backup

# Test on one file
dotnet run --project migration-tool \
  --rules-file migration-rules.json \
  --target-files src/Services/TestService.cs \
  --working-directory .

# Review changes
git diff src/Services/TestService.cs
```

### 2. Incremental Migration

```bash
# Migrate by folders/namespaces
dotnet run --project migration-tool \
  --rules-file migration-rules.json \
  --target-files "src/Controllers/**/*.cs" \
  --working-directory .

git add -A && git commit -m "Migrate Controllers"

dotnet run --project migration-tool \
  --rules-file migration-rules.json \
  --target-files "src/Services/**/*.cs" \
  --working-directory .

git add -A && git commit -m "Migrate Services"
```

### 3. Validation After Migration

```bash
# Ensure project compiles
dotnet build

# Run tests
dotnet test

# Check for common issues
grep -r "using Newtonsoft.Json" src/ || echo "No Newtonsoft.Json references found"
grep -r "AddDelegatingHandler" src/ || echo "No obsolete handler calls found"
```

## Customizing Migration Rules

### Adding Custom Rules

Create your own migration rules by following this pattern:

```json
{
  "rules": [
    {
      "name": "Your custom migration description",
      "target_nodes": [
        {
          "type": "invocationexpression|methoddeclaration|classdeclaration",
          "method_name": "MethodToChange",
          "containing_type": "OptionalClassName"
        }
      ],
      "action": {
        "type": "remove_invocation|rename_method|replace_invocation",
        "replacement_method": "NewMethodName",
        "preserve_parameters": true
      }
    }
  ]
}
```

### Combining Multiple Examples

You can combine rules from multiple examples:

```bash
# Merge multiple rule files
jq -s '{"rules": (map(.rules) | add)}' \
  examples/nuget-migrations/remove-obsolete-methods/migration-rules.json \
  examples/nuget-migrations/method-renames/entity-framework.json \
  > combined-rules.json
```

## Troubleshooting

### Common Issues

1. **"No rules applied"**

   - Check that target node types match exactly
   - Verify method names are spelled correctly
   - Ensure containing type names match

2. **"Syntax errors after migration"**

   - Review the generated code manually
   - Check for missing using statements
   - Verify method chain continuity

3. **"Migration tool not found"**
   - Ensure the C# migration tool is built
   - Check the tool path in your commands
   - Verify .NET SDK is installed

### Getting Help

1. **Check the logs** from the migration tool for specific error messages
2. **Review the examples** to ensure your rules match the expected format
3. **Test with simpler rules** first to isolate issues
4. **Use version control** to easily revert changes if needed

## Contributing

To add new migration examples:

1. Create a new folder under `examples/nuget-migrations/`
2. Include:
   - `README.md` with explanation
   - `migration-rules.json` with the rules
   - `before/` and `after/` folders with code examples
3. Update the main README.md to reference your example
4. Test your rules on real code samples
5. Submit a pull request with your contribution
