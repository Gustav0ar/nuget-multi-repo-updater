# Complex Migration Scenario: ASP.NET Core 2.2 to 6.0

## Overview

This example demonstrates a complex migration scenario involving multiple types of changes when upgrading from ASP.NET Core 2.2 to 6.0, including method renames, parameter changes, type replacements, and obsolete method removal.

## Before Migration

```csharp
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Newtonsoft.Json;

namespace WebApp
{
    public class Startup
    {
        public IConfiguration Configuration { get; }

        public Startup(IConfiguration configuration)
        {
            Configuration = configuration;
        }

        public void ConfigureServices(IServiceCollection services)
        {
            services.AddMvc()
                .AddJsonOptions(options =>
                {
                    options.SerializerSettings.NullValueHandling = NullValueHandling.Ignore;
                });

            services.AddHttpClient<ApiClient>(client =>
            {
                client.BaseAddress = new Uri("https://api.example.com");
            })
            .AddDelegatingHandler<AuthHandler>()
            .AddDelegatingHandler<LoggingHandler>();

            services.AddAuthentication()
                .AddJwtBearer(options =>
                {
                    options.Authority = "https://auth.example.com";
                });
        }

        public void Configure(IApplicationBuilder app, IHostingEnvironment env)
        {
            if (env.IsDevelopment())
            {
                app.UseDeveloperExceptionPage();
            }

            app.UseAuthentication();
            app.UseMvc();
        }
    }

    public class ApiClient
    {
        private readonly HttpClient _httpClient;
        private readonly ILogger<ApiClient> _logger;

        public ApiClient(HttpClient httpClient, ILogger<ApiClient> logger)
        {
            _httpClient = httpClient;
            _logger = logger;
        }

        public async Task<T> GetAsync<T>(string endpoint)
        {
            var response = await _httpClient.GetStringAsync(endpoint);
            return JsonConvert.DeserializeObject<T>(response);
        }

        public async Task PostAsync<T>(string endpoint, T data)
        {
            var json = JsonConvert.SerializeObject(data);
            var content = new StringContent(json, Encoding.UTF8, "application/json");
            await _httpClient.PostAsync(endpoint, content);
        }
    }
}
```

## After Migration

```csharp
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using System.Text.Json;

namespace WebApp
{
    public class Startup
    {
        public IConfiguration Configuration { get; }

        public Startup(IConfiguration configuration)
        {
            Configuration = configuration;
        }

        public void ConfigureServices(IServiceCollection services)
        {
            services.AddControllers()
                .AddJsonOptions(options =>
                {
                    options.JsonSerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull;
                });

            services.AddHttpClient<ApiClient>(client =>
            {
                client.BaseAddress = new Uri("https://api.example.com");
            });
            // Note: Delegating handlers removed, need manual registration with new pattern

            services.AddAuthentication()
                .AddJwtBearer(options =>
                {
                    options.Authority = "https://auth.example.com";
                });
        }

        public void Configure(IApplicationBuilder app, IHostEnvironment env)
        {
            if (env.IsDevelopment())
            {
                app.UseDeveloperExceptionPage();
            }

            app.UseAuthentication();
            app.UseRouting();
            app.UseAuthorization();
            app.MapControllers();
        }
    }

    public class ApiClient
    {
        private readonly HttpClient _httpClient;
        private readonly ILogger<ApiClient> _logger;

        public ApiClient(HttpClient httpClient, ILogger<ApiClient> logger)
        {
            _httpClient = httpClient;
            _logger = logger;
        }

        public async Task<T> GetAsync<T>(string endpoint)
        {
            var response = await _httpClient.GetStringAsync(endpoint);
            return JsonSerializer.Deserialize<T>(response);
        }

        public async Task PostAsync<T>(string endpoint, T data)
        {
            var json = JsonSerializer.Serialize(data);
            var content = new StringContent(json, Encoding.UTF8, "application/json");
            await _httpClient.PostAsync(endpoint, content);
        }
    }
}
```

## Comprehensive Migration Rules

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
    },
    {
      "name": "Replace AddMvc with AddControllers",
      "target_nodes": [
        {
          "type": "invocationexpression",
          "method_name": "AddMvc"
        }
      ],
      "action": {
        "type": "replace_invocation",
        "replacement_method": "AddControllers",
        "preserve_parameters": true
      }
    },
    {
      "name": "Replace UseMvc with UseRouting and MapControllers",
      "target_nodes": [
        {
          "type": "invocationexpression",
          "method_name": "UseMvc"
        }
      ],
      "action": {
        "type": "replace_invocation",
        "replacement_code": "UseRouting();\n            app.UseAuthorization();\n            app.MapControllers",
        "preserve_parameters": false
      }
    },
    {
      "name": "Update IHostingEnvironment to IHostEnvironment",
      "target_nodes": [
        {
          "type": "parameterdeclaration",
          "type": "IHostingEnvironment"
        }
      ],
      "action": {
        "type": "replace_parameter_type",
        "replacement_type": "IHostEnvironment"
      }
    },
    {
      "name": "Replace JsonConvert.SerializeObject with JsonSerializer.Serialize",
      "target_nodes": [
        {
          "type": "invocationexpression",
          "method_name": "SerializeObject",
          "containing_type": "JsonConvert"
        }
      ],
      "action": {
        "type": "replace_invocation",
        "replacement_code": "JsonSerializer.Serialize",
        "preserve_parameters": true
      }
    },
    {
      "name": "Replace JsonConvert.DeserializeObject with JsonSerializer.Deserialize",
      "target_nodes": [
        {
          "type": "invocationexpression",
          "method_name": "DeserializeObject",
          "containing_type": "JsonConvert"
        }
      ],
      "action": {
        "type": "replace_invocation",
        "replacement_code": "JsonSerializer.Deserialize",
        "preserve_parameters": true
      }
    }
  ]
}
```

## Migration Steps

### 1. Automated Changes

The migration tool will handle:

- ✅ Remove `AddDelegatingHandler` calls
- ✅ Replace `AddMvc` with `AddControllers`
- ✅ Update parameter types
- ✅ Replace JSON serialization calls

### 2. Manual Changes Required

After running the migration tool:

1. **Update using statements**:

   ```csharp
   // Remove
   using Newtonsoft.Json;
   using Microsoft.AspNetCore.Hosting;

   // Add
   using System.Text.Json;
   using Microsoft.Extensions.Hosting;
   ```

2. **Update JSON options configuration**:

   ```csharp
   // Old
   options.SerializerSettings.NullValueHandling = NullValueHandling.Ignore;

   // New
   options.JsonSerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull;
   ```

3. **Add routing middleware**:

   ```csharp
   app.UseRouting();
   app.UseAuthorization(); // Add if using authorization
   app.MapControllers(); // Replaces UseMvc()
   ```

4. **Re-register HTTP handlers** (if needed):

   ```csharp
   services.AddHttpClient<ApiClient>()
       .AddHttpMessageHandler<AuthHandler>()
       .AddHttpMessageHandler<LoggingHandler>();

   services.AddTransient<AuthHandler>();
   services.AddTransient<LoggingHandler>();
   ```

## Testing Strategy

### 1. Compilation Testing

- Ensure project compiles without errors
- Verify all using statements are correct
- Check that all types are resolved

### 2. Runtime Testing

- Test HTTP client functionality
- Verify JSON serialization/deserialization
- Test authentication flows
- Verify routing works correctly

### 3. Integration Testing

- Test complete request/response cycles
- Verify middleware pipeline order
- Test error handling scenarios

## Common Issues and Solutions

### Issue: JSON Serialization Differences

**Problem**: System.Text.Json has different defaults than Newtonsoft.Json
**Solution**: Configure JsonSerializerOptions to match previous behavior

### Issue: Routing Changes

**Problem**: UseMvc() is replaced with multiple method calls
**Solution**: Ensure UseRouting(), UseAuthorization(), and MapControllers() are in correct order

### Issue: Handler Registration

**Problem**: AddDelegatingHandler() is obsolete
**Solution**: Use AddHttpMessageHandler() and register handlers in DI

## Performance Considerations

- System.Text.Json is generally faster than Newtonsoft.Json
- New routing system has better performance characteristics
- HTTP client handler registration is more efficient

## Backward Compatibility

Some features may not have direct equivalents:

- Custom JsonConverter implementations need rewriting
- Some Newtonsoft.Json attributes don't exist in System.Text.Json
- Error handling may behave differently
