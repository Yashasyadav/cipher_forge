package com.cipherforge.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final ProgressWebSocketHandler progressWebSocketHandler;

    public WebSocketConfig(ProgressWebSocketHandler progressWebSocketHandler) {
        this.progressWebSocketHandler = progressWebSocketHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(progressWebSocketHandler, "/ws/wipe-progress", "/ws/progress")
                .setAllowedOriginPatterns("http://localhost:*", "http://127.0.0.1:*");
    }
}
