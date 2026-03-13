package com.cipherforge.repositories;

import com.cipherforge.entities.Device;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface DeviceRepository extends JpaRepository<Device, Long> {
    Optional<Device> findByEngineDeviceName(String engineDeviceName);
}


