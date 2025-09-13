using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Http;
using System;

namespace Example.Services
{
    public class Startup
    {
        public void ConfigureServices(IServiceCollection services)
        {
            // Basic HTTP client with obsolete handlers
            services.AddHttpClient<WeatherApiClient>(client =>
            {
                client.BaseAddress = new Uri("https://api.weather.com");
                client.Timeout = TimeSpan.FromSeconds(30);
            })
            .AddDelegatingHandler<AuthenticationHandler>()
            .AddDelegatingHandler<LoggingHandler>()
            .AddDelegatingHandler<RetryHandler>();
            
            // Named HTTP client with obsolete handlers
            services.AddHttpClient("PaymentService", client =>
            {
                client.BaseAddress = new Uri("https://payments.example.com");
            })
            .AddDelegatingHandler<SecurityHandler>()
            .AddDelegatingHandler<AuditHandler>();
            
            // Multiple separate clients
            services.AddHttpClient<UserApiClient>()
                .AddDelegatingHandler<CachingHandler>();
                
            services.AddHttpClient<NotificationClient>(client =>
            {
                client.BaseAddress = new Uri("https://notifications.service.com");
            })
            .AddDelegatingHandler<RateLimitHandler>()
            .AddDelegatingHandler<MetricsHandler>()
            .SetHandlerLifetime(TimeSpan.FromMinutes(5));
        }
    }
    
    public class WeatherApiClient
    {
        private readonly HttpClient _httpClient;
        
        public WeatherApiClient(HttpClient httpClient)
        {
            _httpClient = httpClient;
        }
    }
    
    public class UserApiClient
    {
        private readonly HttpClient _httpClient;
        
        public UserApiClient(HttpClient httpClient)
        {
            _httpClient = httpClient;
        }
    }
    
    public class NotificationClient
    {
        private readonly HttpClient _httpClient;
        
        public NotificationClient(HttpClient httpClient)
        {
            _httpClient = httpClient;
        }
    }
}
