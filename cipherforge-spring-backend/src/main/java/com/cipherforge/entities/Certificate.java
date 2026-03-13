package com.cipherforge.entities;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Lob;
import jakarta.persistence.OneToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import org.hibernate.annotations.UuidGenerator;

import java.time.OffsetDateTime;

@Entity
@Table(name = "certificates")
public class Certificate {

    @Id
    @GeneratedValue
    @UuidGenerator
    private String id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "wipe_job_id", nullable = false, unique = true)
    private WipeJob wipeJob;

    @Column(nullable = false, unique = true, length = 120)
    private String engineCertificateId;

    @Column(nullable = false, length = 200)
    private String deviceSerialNumber;

    @Column(nullable = false, length = 50)
    private String deviceType;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private WipeMethodType wipeMethod;

    @Column(nullable = false)
    private int overwritePasses;

    @Column(nullable = false)
    private OffsetDateTime certificateTimestamp;

    @Column(nullable = false, length = 20)
    private String verificationStatus;

    @Column(nullable = false)
    private int recoveredFiles;

    @Column(nullable = false, length = 128)
    private String sha256Hash;

    @Column(nullable = false, length = 500)
    private String jsonPath;

    @Column(nullable = false, length = 500)
    private String pdfPath;

    @Lob
    @Column(nullable = false)
    private String rawPayload;

    @Column(nullable = false)
    private OffsetDateTime createdAt;

    @PrePersist
    public void onCreate() {
        if (createdAt == null) {
            createdAt = OffsetDateTime.now();
        }
    }

    public String getId() {
        return id;
    }

    public WipeJob getWipeJob() {
        return wipeJob;
    }

    public void setWipeJob(WipeJob wipeJob) {
        this.wipeJob = wipeJob;
    }

    public String getEngineCertificateId() {
        return engineCertificateId;
    }

    public void setEngineCertificateId(String engineCertificateId) {
        this.engineCertificateId = engineCertificateId;
    }

    public String getDeviceSerialNumber() {
        return deviceSerialNumber;
    }

    public void setDeviceSerialNumber(String deviceSerialNumber) {
        this.deviceSerialNumber = deviceSerialNumber;
    }

    public String getDeviceType() {
        return deviceType;
    }

    public void setDeviceType(String deviceType) {
        this.deviceType = deviceType;
    }

    public WipeMethodType getWipeMethod() {
        return wipeMethod;
    }

    public void setWipeMethod(WipeMethodType wipeMethod) {
        this.wipeMethod = wipeMethod;
    }

    public int getOverwritePasses() {
        return overwritePasses;
    }

    public void setOverwritePasses(int overwritePasses) {
        this.overwritePasses = overwritePasses;
    }

    public OffsetDateTime getCertificateTimestamp() {
        return certificateTimestamp;
    }

    public void setCertificateTimestamp(OffsetDateTime certificateTimestamp) {
        this.certificateTimestamp = certificateTimestamp;
    }

    public String getVerificationStatus() {
        return verificationStatus;
    }

    public void setVerificationStatus(String verificationStatus) {
        this.verificationStatus = verificationStatus;
    }

    public int getRecoveredFiles() {
        return recoveredFiles;
    }

    public void setRecoveredFiles(int recoveredFiles) {
        this.recoveredFiles = recoveredFiles;
    }

    public String getSha256Hash() {
        return sha256Hash;
    }

    public void setSha256Hash(String sha256Hash) {
        this.sha256Hash = sha256Hash;
    }

    public String getJsonPath() {
        return jsonPath;
    }

    public void setJsonPath(String jsonPath) {
        this.jsonPath = jsonPath;
    }

    public String getPdfPath() {
        return pdfPath;
    }

    public void setPdfPath(String pdfPath) {
        this.pdfPath = pdfPath;
    }

    public String getRawPayload() {
        return rawPayload;
    }

    public void setRawPayload(String rawPayload) {
        this.rawPayload = rawPayload;
    }

    public OffsetDateTime getCreatedAt() {
        return createdAt;
    }
}


