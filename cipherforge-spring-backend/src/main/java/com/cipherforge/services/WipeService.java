package com.cipherforge.services;

import com.cipherforge.client.WipeEngineClient;
import com.cipherforge.dto.WipeJobStatusResponse;
import com.cipherforge.dto.WipeStartRequest;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class WipeService {

    private final WipeJobService wipeJobService;
    private final WipeEngineClient wipeEngineClient;

    public WipeService(WipeJobService wipeJobService, WipeEngineClient wipeEngineClient) {
        this.wipeJobService = wipeJobService;
        this.wipeEngineClient = wipeEngineClient;
    }

    public WipeJobStatusResponse startWipe(WipeStartRequest request) {
        return wipeJobService.startWipe(request);
    }

    public WipeJobStatusResponse getStatus(String jobId) {
        return wipeJobService.getStatus(jobId);
    }

    public List<WipeJobStatusResponse> listJobs() {
        return wipeJobService.listJobs();
    }

    public List<String> listSupportedMethods() {
        return wipeJobService.listSupportedMethods();
    }

    // Direct engine bridge methods for internal workflows and diagnostics.
    public List<WipeEngineClient.EngineDeviceDto> getDevices() {
        return wipeEngineClient.getDevices();
    }

    public WipeEngineClient.EngineWipeStartDto startWipe(String device, String method) {
        return wipeEngineClient.startWipe(device, method);
    }

    public WipeEngineClient.EngineWipeStatusDto getWipeStatus(String jobId) {
        return wipeEngineClient.getWipeStatus(jobId);
    }
}
