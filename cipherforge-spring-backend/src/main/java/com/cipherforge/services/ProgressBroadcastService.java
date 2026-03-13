package com.cipherforge.services;

import com.cipherforge.config.ProgressWebSocketHandler;
import com.cipherforge.dto.WipeProgressUpdate;
import com.cipherforge.entities.WipeJob;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;

@Service
public class ProgressBroadcastService {

    private static final Logger log = LoggerFactory.getLogger(ProgressBroadcastService.class);
    private final ProgressWebSocketHandler socketHandler;
    private final ObjectMapper objectMapper;

    public ProgressBroadcastService(ProgressWebSocketHandler socketHandler, ObjectMapper objectMapper) {
        this.socketHandler = socketHandler;
        this.objectMapper = objectMapper;
    }

    public void broadcast(WipeJob job, String certificateId) {
        WipeProgressUpdate update = new WipeProgressUpdate(
                job.getId(),
                job.getEngineJobId(),
                job.getDevice().getEngineDeviceName(),
                job.getWipeMethod().name(),
                job.getStatus().name(),
                job.getProgress(),
                job.getStartTime(),
                job.getEndTime(),
                certificateId,
                job.getErrorMessage(),
                OffsetDateTime.now()
        );

        try {
            socketHandler.broadcast(objectMapper.writeValueAsString(update));
        } catch (JsonProcessingException ex) {
            log.warn("Unable to serialize wipe progress update for jobId={}", job.getId(), ex);
        }
    }
}

