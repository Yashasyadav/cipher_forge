package com.cipherforge.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.concurrent.CompletableFuture;

@Component
public class PythonEngineStarter {

    private static final Logger log = LoggerFactory.getLogger(PythonEngineStarter.class);

    private static final String ENGINE_ROOT_PATH = "D:/SIH_2025-main";
    private static final String ENGINE_SCRIPT_PATH = "D:/SIH_2025-main/wipe_engine_service/main.py";
    private static final String ENGINE_HOST = "127.0.0.1";
    private static final int ENGINE_PORT = 8000;

    private volatile Process pythonProcess;

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        CompletableFuture.runAsync(this::startEngineIfNeeded);
    }

    private void startEngineIfNeeded() {
        if (isEngineRunning()) {
            log.info("Python Wipe Engine Already Running");
            return;
        }

        Path scriptPath = Paths.get(ENGINE_SCRIPT_PATH);
        if (!Files.exists(scriptPath)) {
            log.error("Failed to start Python Wipe Engine: script not found at {}", ENGINE_SCRIPT_PATH);
            return;
        }

        Path workingDir = Paths.get(ENGINE_ROOT_PATH);
        if (!Files.isDirectory(workingDir)) {
            log.error("Failed to start Python Wipe Engine: invalid working directory {}", ENGINE_ROOT_PATH);
            return;
        }

        ProcessBuilder processBuilder = new ProcessBuilder("python", "-m", "wipe_engine_service.main");
        processBuilder.directory(workingDir.toFile());
        processBuilder.redirectErrorStream(true);
        processBuilder.redirectOutput(ProcessBuilder.Redirect.DISCARD);

        try {
            pythonProcess = processBuilder.start();
            if (waitForEnginePort(10_000)) {
                log.info("Python Wipe Engine Started");
            } else if (!pythonProcess.isAlive()) {
                log.error("Failed to start Python Wipe Engine: process exited with code {}", pythonProcess.exitValue());
            } else {
                log.error("Failed to confirm Python Wipe Engine startup on {}:{}", ENGINE_HOST, ENGINE_PORT);
            }
        } catch (IOException ex) {
            log.error("Failed to start Python Wipe Engine", ex);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            log.error("Python Wipe Engine startup check was interrupted", ex);
        } catch (Exception ex) {
            log.error("Unexpected error while starting Python Wipe Engine", ex);
        }
    }

    private boolean isEngineRunning() {
        if (pythonProcess != null && pythonProcess.isAlive()) {
            return true;
        }
        return isPortOpen(ENGINE_HOST, ENGINE_PORT, 300);
    }

    private boolean waitForEnginePort(long timeoutMs) throws InterruptedException {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < deadline) {
            if (isPortOpen(ENGINE_HOST, ENGINE_PORT, 300)) {
                return true;
            }
            Thread.sleep(300);
        }
        return isPortOpen(ENGINE_HOST, ENGINE_PORT, 300);
    }

    private boolean isPortOpen(String host, int port, int timeoutMs) {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), timeoutMs);
            return true;
        } catch (IOException ex) {
            return false;
        }
    }
}
