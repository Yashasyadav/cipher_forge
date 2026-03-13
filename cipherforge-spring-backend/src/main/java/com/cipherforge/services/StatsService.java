package com.cipherforge.services;

import com.cipherforge.dto.StatsResponse;
import com.cipherforge.entities.WipeJobStatus;
import com.cipherforge.repositories.CertificateRepository;
import com.cipherforge.repositories.WipeJobRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.EnumSet;

@Service
public class StatsService {

    private final WipeJobRepository wipeJobRepository;
    private final CertificateRepository certificateRepository;

    public StatsService(
            WipeJobRepository wipeJobRepository,
            CertificateRepository certificateRepository
    ) {
        this.wipeJobRepository = wipeJobRepository;
        this.certificateRepository = certificateRepository;
    }

    @Transactional(readOnly = true)
    public StatsResponse getStats() {
        long devicesWiped = wipeJobRepository.countByStatus(WipeJobStatus.COMPLETED);
        long certificatesGenerated = certificateRepository.count();
        long failedJobs = wipeJobRepository.countByStatus(WipeJobStatus.FAILED);
        long activeJobs = wipeJobRepository.countByStatusIn(EnumSet.of(WipeJobStatus.QUEUED, WipeJobStatus.RUNNING));

        return new StatsResponse(
                devicesWiped,
                certificatesGenerated,
                failedJobs,
                activeJobs
        );
    }
}


