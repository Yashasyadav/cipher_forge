package com.cipherforge.config;

import com.cipherforge.entities.Certificate;
import com.cipherforge.entities.Device;
import com.cipherforge.entities.Role;
import com.cipherforge.entities.User;
import com.cipherforge.entities.WipeJob;
import com.cipherforge.entities.WipeJobStatus;
import com.cipherforge.entities.WipeMethodType;
import com.cipherforge.repositories.CertificateRepository;
import com.cipherforge.repositories.DeviceRepository;
import com.cipherforge.repositories.UserRepository;
import com.cipherforge.repositories.WipeJobRepository;
import org.springframework.dao.DataAccessException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;

@Configuration
public class StartupDataSeeder {

    private static final Logger log = LoggerFactory.getLogger(StartupDataSeeder.class);

    @Bean
    @Transactional
    public CommandLineRunner seedCipherForgeData(
            DeviceRepository deviceRepository,
            WipeJobRepository wipeJobRepository,
            CertificateRepository certificateRepository,
            UserRepository userRepository,
            PasswordEncoder passwordEncoder,
            JdbcTemplate jdbcTemplate,
            @Value("${cipherforge.seed-sample-data:false}") boolean seedSampleData
    ) {
        return args -> {
            ensureUsersRoleConstraint(jdbcTemplate);
            cleanupOrphanSeedJobs(jdbcTemplate);

            ensureDefaultUser(userRepository, passwordEncoder, "admin", "admin@cipherforge.local", Role.ADMIN, "admin12345");
            ensureDefaultUser(userRepository, passwordEncoder, "operator", "operator@cipherforge.local", Role.OPERATOR, "operator12345");

            if (!seedSampleData) {
                log.info("Sample data seeding disabled (cipherforge.seed-sample-data=false).");
                return;
            }

            if (deviceRepository.count() > 0 || wipeJobRepository.count() > 0 || certificateRepository.count() > 0) {
                log.info("Sample seed skipped: existing records detected.");
                return;
            }

            Device deviceA = new Device();
            deviceA.setEngineDeviceName("seed-sda");
            deviceA.setDeviceType("SSD");
            deviceA.setSize("512GB");
            deviceA.setSerialNumber("SEED-SSD-0001");
            deviceRepository.save(deviceA);

            Device deviceB = new Device();
            deviceB.setEngineDeviceName("seed-sdb");
            deviceB.setDeviceType("HDD");
            deviceB.setSize("1TB");
            deviceB.setSerialNumber("SEED-HDD-0002");
            deviceRepository.save(deviceB);

            OffsetDateTime now = OffsetDateTime.now();

            WipeJob completedJob = new WipeJob();
            completedJob.setDevice(deviceA);
            completedJob.setWipeMethod(WipeMethodType.DOD);
            completedJob.setStatus(WipeJobStatus.COMPLETED);
            completedJob.setProgress(100.0);
            completedJob.setEngineJobId("seed-engine-job-0001");
            completedJob.setStartTime(now.minusHours(2));
            completedJob.setEndTime(now.minusHours(1));
            wipeJobRepository.save(completedJob);

            WipeJob failedJob = new WipeJob();
            failedJob.setDevice(deviceB);
            failedJob.setWipeMethod(WipeMethodType.NIST);
            failedJob.setStatus(WipeJobStatus.FAILED);
            failedJob.setProgress(35.0);
            failedJob.setEngineJobId("seed-engine-job-0002");
            failedJob.setStartTime(now.minusMinutes(20));
            failedJob.setEndTime(now.minusMinutes(5));
            failedJob.setErrorMessage("Sample historical failed job");
            wipeJobRepository.save(failedJob);

            Certificate certificate = new Certificate();
            certificate.setWipeJob(completedJob);
            certificate.setEngineCertificateId("seed-cert-0001");
            certificate.setDeviceSerialNumber(deviceA.getSerialNumber());
            certificate.setDeviceType(deviceA.getDeviceType());
            certificate.setWipeMethod(completedJob.getWipeMethod());
            certificate.setOverwritePasses(3);
            certificate.setCertificateTimestamp(now.minusHours(1));
            certificate.setVerificationStatus("PASSED");
            certificate.setRecoveredFiles(0);
            certificate.setSha256Hash("7f83b1657ff1fc53b92dc18148a1d65dfa135014a89f85d67f5f8f3f7fdbf8f6");
            certificate.setJsonPath("certificates/seed-cert-0001.json");
            certificate.setPdfPath("certificates/seed-cert-0001.pdf");
            certificate.setRawPayload("{\"seed\":true,\"verification\":\"PASSED\"}");
            certificateRepository.save(certificate);

            log.info("Sample seed created: devices=2, wipeJobs=2, certificates=1");
        };
    }

    private void ensureUsersRoleConstraint(JdbcTemplate jdbcTemplate) {
        try {
            jdbcTemplate.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check");
            jdbcTemplate.execute(
                    "ALTER TABLE users ADD CONSTRAINT users_role_check " +
                            "CHECK (role IN ('ADMIN','OPERATOR','USER'))"
            );
            log.info("users.role check constraint synced for ADMIN/OPERATOR/USER.");
        } catch (DataAccessException ex) {
            log.warn("Could not sync users.role constraint automatically: {}", ex.getMessage());
        }
    }

    private void cleanupOrphanSeedJobs(JdbcTemplate jdbcTemplate) {
        try {
            int updated = jdbcTemplate.update(
                    "UPDATE wipe_jobs " +
                            "SET status = 'FAILED', " +
                            "    end_time = COALESCE(end_time, NOW()), " +
                            "    error_message = COALESCE(error_message, 'Seed job auto-closed (engine job not available)') " +
                            "WHERE engine_job_id LIKE 'seed-engine-job-%' " +
                            "  AND status IN ('QUEUED', 'RUNNING')"
            );
            if (updated > 0) {
                log.info("Auto-closed {} orphan seed wipe job(s) to prevent repeated status polling.", updated);
            }
        } catch (DataAccessException ex) {
            log.warn("Could not auto-close orphan seed jobs: {}", ex.getMessage());
        }
    }

    private void ensureDefaultUser(
            UserRepository userRepository,
            PasswordEncoder passwordEncoder,
            String username,
            String email,
            Role role,
            String rawPassword
    ) {
        User user = userRepository.findByUsername(username).orElseGet(User::new);
        boolean isNew = user.getId() == null;

        if (isNew) {
            user.setUsername(username);
            user.setEmail(email);
        } else if (user.getEmail() == null || user.getEmail().isBlank()) {
            user.setEmail(email);
        }

        // Keep seeded credentials stable in local dev so login always works.
        user.setRole(role);
        user.setPasswordHash(passwordEncoder.encode(rawPassword));
        userRepository.save(user);

        log.info("Default user {} synced as role={}", username, role.name());
    }
}
