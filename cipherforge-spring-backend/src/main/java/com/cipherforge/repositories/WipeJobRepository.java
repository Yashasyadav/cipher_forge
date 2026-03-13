package com.cipherforge.repositories;

import com.cipherforge.entities.WipeJob;
import com.cipherforge.entities.WipeJobStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

public interface WipeJobRepository extends JpaRepository<WipeJob, String> {
    Optional<WipeJob> findByEngineJobId(String engineJobId);
    long countByStatus(WipeJobStatus status);
    long countByStatusIn(Collection<WipeJobStatus> statuses);
    List<WipeJob> findByStatusIn(Collection<WipeJobStatus> statuses);
}

