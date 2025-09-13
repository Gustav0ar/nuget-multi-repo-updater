# ASP.NET Core Middleware Parameter Updates

## Overview

ASP.NET Core middleware signatures sometimes change between versions, requiring updates to method parameters. This example shows how to handle common middleware parameter changes.

## Before Migration

```csharp
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using System.Threading.Tasks;

public class CustomMiddleware
{
    private readonly RequestDelegate _next;

    public CustomMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        // Pre-processing
        await LogRequest(context);

        await _next(context);

        // Post-processing
        await LogResponse(context);
    }

    private async Task LogRequest(HttpContext context)
    {
        // Old logging approach
        var request = context.Request;
        await Task.Delay(1); // Simulate async work
    }

    private async Task LogResponse(HttpContext context)
    {
        // Old logging approach
        var response = context.Response;
        await Task.Delay(1); // Simulate async work
    }
}

public static class MiddlewareExtensions
{
    public static IApplicationBuilder UseCustomMiddleware(this IApplicationBuilder builder)
    {
        return builder.UseMiddleware<CustomMiddleware>();
    }

    // Old signature with fewer parameters
    public static IApplicationBuilder UseCustomAuth(this IApplicationBuilder builder, string scheme)
    {
        return builder.Use(async (context, next) =>
        {
            // Old authentication logic
            await next();
        });
    }
}
```

## After Migration

```csharp
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using System.Threading.Tasks;

public class CustomMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ILogger<CustomMiddleware> _logger;

    public CustomMiddleware(RequestDelegate next, ILogger<CustomMiddleware> logger)
    {
        _next = next;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        // Pre-processing with enhanced logging
        await LogRequest(context);

        await _next(context);

        // Post-processing with enhanced logging
        await LogResponse(context);
    }

    private async Task LogRequest(HttpContext context)
    {
        // Enhanced logging approach
        _logger.LogInformation("Processing request {Path}", context.Request.Path);
        await Task.Delay(1); // Simulate async work
    }

    private async Task LogResponse(HttpContext context)
    {
        // Enhanced logging approach
        _logger.LogInformation("Response status {StatusCode}", context.Response.StatusCode);
        await Task.Delay(1); // Simulate async work
    }
}

public static class MiddlewareExtensions
{
    public static IApplicationBuilder UseCustomMiddleware(this IApplicationBuilder builder)
    {
        return builder.UseMiddleware<CustomMiddleware>();
    }

    // New signature with additional parameters
    public static IApplicationBuilder UseCustomAuth(this IApplicationBuilder builder, string scheme, AuthenticationOptions options)
    {
        return builder.Use(async (context, next) =>
        {
            // Enhanced authentication logic with options
            await next();
        });
    }
}
```

## Migration Rules

```json
{
  "rules": [
    {
      "name": "Add ILogger parameter to middleware constructors",
      "target_nodes": [
        {
          "type": "methoddeclaration",
          "method_name": "CustomMiddleware",
          "containing_type": "CustomMiddleware"
        }
      ],
      "action": {
        "type": "replace_method_signature",
        "replacement_code": "public CustomMiddleware(RequestDelegate next, ILogger<CustomMiddleware> logger)"
      }
    },
    {
      "name": "Update UseCustomAuth method signature",
      "target_nodes": [
        {
          "type": "methoddeclaration",
          "method_name": "UseCustomAuth"
        }
      ],
      "action": {
        "type": "replace_method_signature",
        "replacement_code": "public static IApplicationBuilder UseCustomAuth(this IApplicationBuilder builder, string scheme, AuthenticationOptions options)"
      }
    }
  ]
}
```

## Common Parameter Change Patterns

### 1. Adding Dependency Injection Parameters

**Before:**

```csharp
public CustomService(IConfiguration config)
{
    _config = config;
}
```

**After:**

```csharp
public CustomService(IConfiguration config, ILogger<CustomService> logger, IOptions<CustomOptions> options)
{
    _config = config;
    _logger = logger;
    _options = options.Value;
}
```

### 2. Options Pattern Migration

**Before:**

```csharp
public void ConfigureAuth(string issuer, string audience)
{
    // Direct parameter usage
}
```

**After:**

```csharp
public void ConfigureAuth(JwtOptions jwtOptions)
{
    // Options pattern usage
    var issuer = jwtOptions.Issuer;
    var audience = jwtOptions.Audience;
}
```

### 3. Async Method Updates

**Before:**

```csharp
public bool ProcessData(string data)
{
    // Synchronous processing
    return true;
}
```

**After:**

```csharp
public async Task<bool> ProcessDataAsync(string data, CancellationToken cancellationToken = default)
{
    // Asynchronous processing with cancellation support
    await Task.Delay(100, cancellationToken);
    return true;
}
```

## Manual Steps Required

After running automated migrations:

1. **Update method bodies** to use new parameters
2. **Add field declarations** for injected dependencies
3. **Update calling code** to pass new parameters
4. **Add using statements** for new types
5. **Update unit tests** to mock new dependencies
6. **Update dependency injection registrations**

## Example Complete Update

### Before

```csharp
public class EmailService
{
    public void SendEmail(string to, string subject, string body)
    {
        // Simple email sending
    }
}
```

### After

```csharp
public class EmailService
{
    private readonly ILogger<EmailService> _logger;
    private readonly IOptions<EmailOptions> _options;

    public EmailService(ILogger<EmailService> logger, IOptions<EmailOptions> options)
    {
        _logger = logger;
        _options = options;
    }

    public async Task SendEmailAsync(string to, string subject, string body, CancellationToken cancellationToken = default)
    {
        _logger.LogInformation("Sending email to {Recipient}", to);

        // Enhanced email sending with options and async support
        await Task.Delay(100, cancellationToken);

        _logger.LogInformation("Email sent successfully");
    }
}
```

## Testing Strategy

1. **Update unit tests** to provide new dependencies
2. **Test dependency injection** container configuration
3. **Verify new parameters** are being used correctly
4. **Test cancellation scenarios** if CancellationToken was added
5. **Validate logging output** if logging was added
6. **Performance test** if moving from sync to async
