package com.cipherforge.entities;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

import java.time.OffsetDateTime;

@Entity
@Table(name = "devices")
public class Device {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 200)
    private String engineDeviceName;

    @Column(nullable = false, length = 50)
    private String deviceType;

    @Column(nullable = false, length = 50)
    private String size;

    @Column(nullable = false, length = 200)
    private String serialNumber;

    @Column(nullable = false)
    private OffsetDateTime lastSeenAt;

    @PrePersist
    @PreUpdate
    public void touch() {
        lastSeenAt = OffsetDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public String getEngineDeviceName() {
        return engineDeviceName;
    }

    public void setEngineDeviceName(String engineDeviceName) {
        this.engineDeviceName = engineDeviceName;
    }

    public String getDeviceType() {
        return deviceType;
    }

    public void setDeviceType(String deviceType) {
        this.deviceType = deviceType;
    }

    public String getSize() {
        return size;
    }

    public void setSize(String size) {
        this.size = size;
    }

    public String getSerialNumber() {
        return serialNumber;
    }

    public void setSerialNumber(String serialNumber) {
        this.serialNumber = serialNumber;
    }

    public OffsetDateTime getLastSeenAt() {
        return lastSeenAt;
    }
}


