package com.cipherforge.services;

import com.cipherforge.client.WipeEngineClient;
import com.cipherforge.dto.DeviceResponse;
import com.cipherforge.entities.Device;
import com.cipherforge.exception.ResourceNotFoundException;
import com.cipherforge.repositories.DeviceRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

@Service
public class DeviceService {

    private static final Logger log = LoggerFactory.getLogger(DeviceService.class);
    private final DeviceRepository deviceRepository;
    private final WipeEngineClient engineClient;

    public DeviceService(DeviceRepository deviceRepository, WipeEngineClient engineClient) {
        this.deviceRepository = deviceRepository;
        this.engineClient = engineClient;
    }

    @Transactional
    public List<DeviceResponse> syncAndListDevices() {
        try {
            List<WipeEngineClient.EngineDeviceDto> engineDevices = engineClient.getDevices();

            for (WipeEngineClient.EngineDeviceDto engineDevice : engineDevices) {
                Device device = deviceRepository.findByEngineDeviceName(engineDevice.device())
                        .orElseGet(Device::new);
                device.setEngineDeviceName(engineDevice.device());
                device.setDeviceType(orUnknown(engineDevice.type()));
                device.setSize(orUnknown(engineDevice.size()));
                device.setSerialNumber(orUnknown(engineDevice.serial()));
                deviceRepository.save(device);
            }

            log.info("Device sync completed. {} devices from engine", engineDevices.size());

            // Return live engine snapshot to avoid showing stale historical rows.
            return engineDevices.stream()
                    .map(engineDevice -> deviceRepository.findByEngineDeviceName(engineDevice.device()).orElse(null))
                    .filter(device -> device != null)
                    .map(this::toResponse)
                    .collect(Collectors.toList());
        } catch (Exception ex) {
            log.warn("Device sync skipped because wipe engine is unavailable. Returning cached devices.", ex);
        }

        return deviceRepository.findAll().stream().map(this::toResponse).toList();
    }

    @Transactional
    public Device getOrSyncByEngineName(String deviceName) {
        return deviceRepository.findByEngineDeviceName(deviceName)
                .orElseGet(() -> {
                    syncAndListDevices();
                    return deviceRepository.findByEngineDeviceName(deviceName)
                            .orElseThrow(() -> new ResourceNotFoundException("Device not found: " + deviceName));
                });
    }

    private DeviceResponse toResponse(Device d) {
        return new DeviceResponse(
                d.getId(),
                d.getEngineDeviceName(),
                d.getDeviceType(),
                d.getSize(),
                d.getSerialNumber(),
                d.getLastSeenAt()
        );
    }

    private String orUnknown(String value) {
        return value == null || value.isBlank() ? "UNKNOWN" : value;
    }
}


