package com.cipherforge.entities;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import org.hibernate.annotations.UuidGenerator;

import java.time.OffsetDateTime;

@Entity
@Table(name = "wipe_jobs")
public class WipeJob {

    @Id
    @GeneratedValue
    @UuidGenerator
    private String id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "device_id")
    private Device device;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private WipeMethodType wipeMethod;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private WipeJobStatus status;

    @Column(nullable = false)
    private double progress;

    @Column(nullable = false, unique = true, length = 120)
    private String engineJobId;

    @Column
    private OffsetDateTime startTime;

    @Column
    private OffsetDateTime endTime;

    @Column(length = 1000)
    private String errorMessage;

    @Column(nullable = false)
    private OffsetDateTime createdAt;

    @Column(nullable = false)
    private OffsetDateTime updatedAt;

    @PrePersist
    public void onCreate() {
        OffsetDateTime now = OffsetDateTime.now();
        createdAt = now;
        updatedAt = now;
        if (status == null) {
            status = WipeJobStatus.QUEUED;
        }
    }

    @PreUpdate
    public void onUpdate() {
        updatedAt = OffsetDateTime.now();
    }

    public String getId() {
        return id;
    }

    public Device getDevice() {
        return device;
    }

    public void setDevice(Device device) {
        this.device = device;
    }

    public WipeMethodType getWipeMethod() {
        return wipeMethod;
    }

    public void setWipeMethod(WipeMethodType wipeMethod) {
        this.wipeMethod = wipeMethod;
    }

    public WipeJobStatus getStatus() {
        return status;
    }

    public void setStatus(WipeJobStatus status) {
        this.status = status;
    }

    public double getProgress() {
        return progress;
    }

    public void setProgress(double progress) {
        this.progress = progress;
    }

    public String getEngineJobId() {
        return engineJobId;
    }

    public void setEngineJobId(String engineJobId) {
        this.engineJobId = engineJobId;
    }

    public OffsetDateTime getStartTime() {
        return startTime;
    }

    public void setStartTime(OffsetDateTime startTime) {
        this.startTime = startTime;
    }

    public OffsetDateTime getEndTime() {
        return endTime;
    }

    public void setEndTime(OffsetDateTime endTime) {
        this.endTime = endTime;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public void setErrorMessage(String errorMessage) {
        this.errorMessage = errorMessage;
    }

    public OffsetDateTime getCreatedAt() {
        return createdAt;
    }

    public OffsetDateTime getUpdatedAt() {
        return updatedAt;
    }
}


