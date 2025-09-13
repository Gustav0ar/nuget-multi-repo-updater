# NuGet Migration Examples

This folder contains examples of common migration scenarios when updating NuGet packages. Each example includes:

- **Before**: Code using the old API
- **After**: Code using the new API
- **Migration Rules**: JSON configuration for the migration tool
- **Description**: Explanation of what changed and why

## Common Migration Scenarios

### 1. Method Removal

- [Remove obsolete AddDelegatingHandler calls](./remove-obsolete-methods/README.md)
- [Remove deprecated ConfigureServices methods](./remove-obsolete-methods/configure-services.md)

### 2. Method Renaming

- [Entity Framework Core method renames](./method-renames/entity-framework.md)
- [ASP.NET Core service registration updates](./method-renames/aspnet-core.md)

### 3. Type Replacements

- [Microsoft.Extensions.Logging type updates](./type-replacements/logging.md)
- [System.Text.Json migration from Newtonsoft.Json](./type-replacements/json-serialization.md)

### 4. Parameter Changes

- [ASP.NET Core middleware parameter updates](./parameter-changes/middleware.md)
- [Entity Framework configuration parameter changes](./parameter-changes/entity-framework.md)

### 5. Namespace Changes

- [Microsoft.AspNetCore namespace consolidation](./namespace-changes/aspnetcore.md)
- [Microsoft.Extensions namespace updates](./namespace-changes/extensions.md)

## Using These Examples

1. **Copy the migration rules** from the relevant example
2. **Adapt the rules** to your specific package versions and requirements
3. **Test the migration** on a small subset of files first
4. **Run the migration tool** with the configured rules

## Migration Rules Format

Each example includes a `migration-rules.json` file with the following structure:

```json
{
  "rules": [
    {
      "name": "Description of the migration",
      "target_nodes": [
        {
          "type": "invocationexpression|methoddeclaration|classdeclaration",
          "method_name": "MethodName",
          "containing_type": "ClassName"
        }
      ],
      "action": {
        "type": "remove_invocation|rename_method|replace_invocation",
        "replacement_method": "NewMethodName",
        "replacement_code": "NewCode()"
      }
    }
  ]
}
```

## Testing Your Migrations

Before applying migrations to your entire codebase:

1. Create a backup of your code
2. Test on a single file or small directory
3. Review the changes carefully
4. Run your tests to ensure functionality is preserved
5. Commit changes incrementally

## Contributing Examples

If you have additional migration scenarios that would be helpful, please contribute them following the same structure:

- `README.md` - Explanation and overview
- `before/` - Code examples before migration
- `after/` - Code examples after migration
- `migration-rules.json` - Migration tool configuration
