# Remove Obsolete AddDelegatingHandler Method Calls

## Overview

When updating HTTP client libraries (like Microsoft.Extensions.Http), the `AddDelegatingHandler` method may become obsolete in favor of newer registration patterns. This example shows how to automatically remove these obsolete method calls.

## Before Migration

```csharp
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Http;

public class Startup
{
    public void ConfigureServices(IServiceCollection services)
    {
        services.AddHttpClient<MyApiClient>(client =>
        {
            client.BaseAddress = new Uri("https://api.example.com");
        })
        .AddDelegatingHandler<AuthenticationHandler>()  // Obsolete method
        .AddDelegatingHandler<LoggingHandler>();         // Obsolete method

        // Other service registrations
        services.AddHttpClient("NamedClient")
            .AddDelegatingHandler<RetryHandler>();       // Obsolete method
    }
}
```

## After Migration

```csharp
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Http;

public class Startup
{
    public void ConfigureServices(IServiceCollection services)
    {
        services.AddHttpClient<MyApiClient>(client =>
        {
            client.BaseAddress = new Uri("https://api.example.com");
        });

        // Handlers should now be registered separately or using new patterns
        // See documentation for the updated registration approach

        // Other service registrations
        services.AddHttpClient("NamedClient");
    }
}
```

## Migration Rules

```json
{
  "rules": [
    {
      "name": "Remove obsolete AddDelegatingHandler calls",
      "target_nodes": [
        {
          "type": "invocationexpression",
          "method_name": "AddDelegatingHandler"
        }
      ],
      "action": {
        "type": "remove_invocation",
        "strategy": "smart_chain_aware"
      }
    }
  ]
}
```

## What This Migration Does

1. **Identifies** all calls to the `AddDelegatingHandler` method
2. **Removes** these method calls from method chains
3. **Preserves** the rest of the method chain structure
4. **Maintains** proper code formatting

## Smart Chain Handling

The `smart_chain_aware` strategy ensures that:

- Method chains remain syntactically correct
- Trailing dots and commas are handled properly
- Indentation is preserved
- The migration doesn't break the fluent API pattern

## Manual Steps Required

After running this migration, you may need to:

1. **Update handler registration** to use the new recommended pattern
2. **Add proper service registrations** for the handlers themselves
3. **Update using statements** if needed
4. **Test HTTP client functionality** to ensure handlers still work as expected

## Example Complete Update

If you need to register handlers using the new pattern, consider this approach:

```csharp
// New recommended pattern (manual update after migration)
services.AddHttpClient<MyApiClient>(client =>
{
    client.BaseAddress = new Uri("https://api.example.com");
})
.ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler())
.AddHttpMessageHandler<AuthenticationHandler>()
.AddHttpMessageHandler<LoggingHandler>();

// Register handlers in DI
services.AddTransient<AuthenticationHandler>();
services.AddTransient<LoggingHandler>();
```

## Testing

After migration:

1. Ensure your project compiles without errors
2. Run unit tests for HTTP client functionality
3. Test actual HTTP requests to verify handlers still work
4. Check that dependency injection resolves all required services
