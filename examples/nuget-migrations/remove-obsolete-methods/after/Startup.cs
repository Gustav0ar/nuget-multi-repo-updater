using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Http;
using System;

namespace Example.Services
{
    public class Startup
    {
        public void ConfigureServices(IServiceCollection services)
        {
            // Basic HTTP client with obsolete handlers removed
            services.AddHttpClient<WeatherApiClient>(client =>
            {
                client.BaseAddress = new Uri("https://api.weather.com");
                client.Timeout = TimeSpan.FromSeconds(30);
            });
            
            // Named HTTP client with obsolete handlers removed
            services.AddHttpClient("PaymentService", client =>
            {
                client.BaseAddress = new Uri("https://payments.example.com");
            });
            
            // Multiple separate clients
            services.AddHttpClient<UserApiClient>();
                
            services.AddHttpClient<NotificationClient>(client =>
            {
                client.BaseAddress = new Uri("https://notifications.service.com");
            })
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
