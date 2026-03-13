package com.cipherforge.repositories;

import com.cipherforge.entities.Certificate;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface CertificateRepository extends JpaRepository<Certificate, String> {
    Optional<Certificate> findByEngineCertificateId(String engineCertificateId);
    Optional<Certificate> findByWipeJob_Id(String wipeJobId);
}

