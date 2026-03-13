package com.cipherforge.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;
import java.util.Iterator;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class ProgressWebSocketHandler extends TextWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(ProgressWebSocketHandler.class);
    private final Set<WebSocketSession> sessions = ConcurrentHashMap.newKeySet();

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        sessions.add(session);
        log.debug("Progress WebSocket connected. sessionId={} activeSessions={}", session.getId(), sessions.size());
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        sessions.remove(session);
        log.debug("Progress WebSocket disconnected. sessionId={} activeSessions={}", session.getId(), sessions.size());
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) {
        sessions.remove(session);
        log.warn("Progress WebSocket transport error. sessionId={} message={}", session.getId(), exception.getMessage());
        try {
            session.close(CloseStatus.SERVER_ERROR);
        } catch (IOException ignored) {
        }
    }

    public void broadcast(String payload) {
        if (sessions.isEmpty()) {
            return;
        }

        TextMessage textMessage = new TextMessage(payload);
        Iterator<WebSocketSession> iterator = sessions.iterator();
        while (iterator.hasNext()) {
            WebSocketSession session = iterator.next();
            if (!session.isOpen()) {
                iterator.remove();
                continue;
            }
            try {
                synchronized (session) {
                    session.sendMessage(textMessage);
                }
            } catch (Exception ex) {
                iterator.remove();
                log.debug("Dropping stale WebSocket sessionId={} after send error: {}", session.getId(), ex.getMessage());
            }
        }
    }
}

