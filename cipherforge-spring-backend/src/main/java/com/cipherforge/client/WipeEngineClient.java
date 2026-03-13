package com.cipherforge.client;

import com.cipherforge.exception.ExternalServiceException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import java.util.List;
import java.util.Map;

@Service
public class WipeEngineClient {

    private static final Logger log = LoggerFactory.getLogger(WipeEngineClient.class);
    private final WebClient webClient;

    public WipeEngineClient(WebClient pythonEngineWebClient) {
        this.webClient = pythonEngineWebClient;
    }

    public List<EngineDeviceDto> getDevices() {
        try {
            return webClient.get()
                    .uri("/devices")
                    .retrieve()
                    .bodyToMono(new ParameterizedTypeReference<List<EngineDeviceDto>>() {
                    })
                    .blockOptional()
                    .orElse(List.of());
        } catch (WebClientRequestException ex) {
            log.warn("Unable to connect to wipe engine while fetching devices: {}", ex.getMessage());
            return List.of();
        } catch (WebClientResponseException ex) {
            log.warn("Wipe engine returned {} while fetching devices: {}", ex.getStatusCode().value(), ex.getResponseBodyAsString());
            return List.of();
        }
    }

    // Backward-compatible alias for older callers.
    public List<EngineDeviceDto> fetchDevices() {
        return getDevices();
    }

    public EngineWipeStartDto startWipe(String device, String method) {
        try {
            return webClient.post()
                    .uri("/wipe")
                    .bodyValue(Map.of("device", device, "method", method))
                    .retrieve()
                    .bodyToMono(EngineWipeStartDto.class)
                    .blockOptional()
                    .orElseThrow(() -> new ExternalServiceException("Empty response from wipe engine while starting job"));
        } catch (WebClientRequestException ex) {
            throw new ExternalServiceException("Unable to connect to wipe engine at /wipe", ex);
        } catch (WebClientResponseException ex) {
            throw new ExternalServiceException("Wipe engine rejected start request: HTTP " + ex.getStatusCode().value(), ex);
        }
    }

    public EngineWipeStatusDto getWipeStatus(String engineJobId) {
        try {
            return webClient.get()
                    .uri("/wipe/status/{jobId}", engineJobId)
                    .retrieve()
                    .bodyToMono(EngineWipeStatusDto.class)
                    .blockOptional()
                    .orElseThrow(() -> new ExternalServiceException("Empty status response from wipe engine"));
        } catch (WebClientRequestException ex) {
            throw new ExternalServiceException("Unable to connect to wipe engine at /wipe/status/" + engineJobId, ex);
        } catch (WebClientResponseException ex) {
            throw new ExternalServiceException("Wipe engine status lookup failed: HTTP " + ex.getStatusCode().value(), ex);
        }
    }

    public EngineCertificateDto fetchCertificate(String certificateId) {
        try {
            return webClient.get()
                    .uri("/certificate/{id}", certificateId)
                    .retrieve()
                    .bodyToMono(EngineCertificateDto.class)
                    .blockOptional()
                    .orElseThrow(() -> new ExternalServiceException("Empty certificate response from wipe engine"));
        } catch (WebClientRequestException ex) {
            throw new ExternalServiceException("Unable to connect to wipe engine at /certificate/" + certificateId, ex);
        } catch (WebClientResponseException ex) {
            throw new ExternalServiceException("Wipe engine certificate lookup failed: HTTP " + ex.getStatusCode().value(), ex);
        }
    }

    public EngineCertificateDto fetchCertificateByJobId(String jobId) {
        try {
            return webClient.get()
                    .uri("/certificate/{jobId}", jobId)
                    .retrieve()
                    .bodyToMono(EngineCertificateDto.class)
                    .blockOptional()
                    .orElseThrow(() -> new ExternalServiceException("Empty certificate response from wipe engine"));
        } catch (WebClientRequestException ex) {
            throw new ExternalServiceException("Unable to connect to wipe engine at /certificate/" + jobId, ex);
        } catch (WebClientResponseException ex) {
            throw new ExternalServiceException("Wipe engine certificate lookup failed: HTTP " + ex.getStatusCode().value(), ex);
        }
    }

    public record EngineDeviceDto(
            String device,
            String type,
            String size,
            String serial
    ) {
    }

    public record EngineWipeStartDto(
            String job_id,
            String device,
            String wipe_method,
            String method,
            String status,
            double progress,
            String start_time,
            String end_time,
            String certificate_id,
            String last_message,
            String error
    ) {
    }

    public record EngineWipeStatusDto(
            String job_id,
            String device,
            String wipe_method,
            String method,
            String status,
            double progress,
            String start_time,
            String end_time,
            String certificate_id,
            String last_message,
            String error
    ) {
    }

    public record EngineCertificateDto(
            String id,
            String job_id,
            String device,
            String device_serial_number,
            String device_type,
            String wipe_method,
            Integer overwrite_passes,
            String timestamp,
            String verification_status,
            Integer recovered_files,
            String sha256_hash,
            String json_path,
            String pdf_path
    ) {
    }
}


