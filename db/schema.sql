CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE departments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    name VARCHAR(200) NOT NULL,

    CONSTRAINT uq_departments_name
        UNIQUE (name),

    CONSTRAINT chk_departments_name_not_empty
        CHECK (length(trim(name)) > 0)
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    university_id VARCHAR(32) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL,
    phone VARCHAR(32),

    role VARCHAR(32) NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt VARCHAR(64) NOT NULL,
    password_changed_at TIMESTAMPTZ,

    department_id UUID,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_users_university_id
        UNIQUE (university_id),

    CONSTRAINT uq_users_email
        UNIQUE (email),

    CONSTRAINT fk_users_department
        FOREIGN KEY (department_id)
        REFERENCES departments(id)
        ON DELETE SET NULL,

    CONSTRAINT chk_users_role
        CHECK (
            role IN (
                'student',
                'employee',
                'service_admin',
                'technical_admin'
            )
        ),

    CONSTRAINT chk_users_full_name_not_empty
        CHECK (length(trim(full_name)) > 0),

    CONSTRAINT chk_users_email_not_empty
        CHECK (length(trim(email)) > 0),

    CONSTRAINT chk_users_password_hash_not_empty
        CHECK (length(trim(password_hash)) > 0),

    CONSTRAINT chk_users_password_salt_not_empty
        CHECK (length(trim(password_salt)) > 0)
);

CREATE TABLE applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    applicant_id UUID NOT NULL,
    support_type VARCHAR(32) NOT NULL,
    academic_year SMALLINT NOT NULL,

    status VARCHAR(32) NOT NULL DEFAULT 'draft',

    requested_amount NUMERIC(12, 2),
    approved_amount NUMERIC(12, 2),

    comment TEXT,
    decision_comment TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    reviewed_by UUID,
    reviewed_at TIMESTAMPTZ,

    version INTEGER NOT NULL DEFAULT 1,

    CONSTRAINT fk_applications_applicant
        FOREIGN KEY (applicant_id)
        REFERENCES users(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_applications_reviewer
        FOREIGN KEY (reviewed_by)
        REFERENCES users(id)
        ON DELETE SET NULL,

    CONSTRAINT chk_applications_support_type
        CHECK (
            support_type IN (
                'material_support',
                'state_academic_scholarship',
                'pgas'
            )
        ),

    CONSTRAINT chk_applications_academic_year
        CHECK (academic_year BETWEEN 2000 AND 2100),

    CONSTRAINT chk_applications_status
        CHECK (
            status IN (
                'draft',
                'submitted',
                'under_review',
                'approved',
                'rejected',
                'cancelled'
            )
        ),

    CONSTRAINT chk_applications_requested_amount
        CHECK (
            requested_amount IS NULL
            OR requested_amount > 0
        ),

    CONSTRAINT chk_applications_approved_amount
        CHECK (
            approved_amount IS NULL
            OR approved_amount > 0
        ),

    CONSTRAINT chk_applications_approved_not_greater_than_requested
        CHECK (
            approved_amount IS NULL
            OR requested_amount IS NULL
            OR approved_amount <= requested_amount
        ),

    CONSTRAINT chk_applications_submitted_at
        CHECK (
            status = 'draft'
            OR submitted_at IS NOT NULL
        ),

    CONSTRAINT chk_applications_review_data
        CHECK (
            (reviewed_by IS NULL AND reviewed_at IS NULL)
            OR
            (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
        ),

    CONSTRAINT chk_applications_version
        CHECK (version > 0)
);

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    application_id UUID NOT NULL,
    uploaded_by UUID NOT NULL,

    original_name VARCHAR(255) NOT NULL,
    storage_key VARCHAR(500) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    file_size BIGINT NOT NULL,
    sha256_hash CHAR(64) NOT NULL,

    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_documents_application
        FOREIGN KEY (application_id)
        REFERENCES applications(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_documents_uploader
        FOREIGN KEY (uploaded_by)
        REFERENCES users(id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_documents_storage_key
        UNIQUE (storage_key),

    CONSTRAINT chk_documents_file_size
        CHECK (file_size > 0),

    CONSTRAINT chk_documents_sha256_hash
        CHECK (sha256_hash ~ '^[0-9a-fA-F]{64}$'),

    CONSTRAINT chk_documents_original_name_not_empty
        CHECK (length(trim(original_name)) > 0),

    CONSTRAINT chk_documents_mime_type_not_empty
        CHECK (length(trim(mime_type)) > 0)
);

CREATE TABLE llm_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    application_id UUID NOT NULL,
    requested_by UUID NOT NULL,

    check_type VARCHAR(32) NOT NULL DEFAULT 'completeness',
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    is_complete BOOLEAN NOT NULL DEFAULT FALSE,

    issues JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,

    model_version VARCHAR(100),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,

    CONSTRAINT fk_llm_checks_application
        FOREIGN KEY (application_id)
        REFERENCES applications(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_llm_checks_requested_by
        FOREIGN KEY (requested_by)
        REFERENCES users(id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_llm_checks_type
        CHECK (
            check_type IN (
                'completeness',
                'consistency'
            )
        ),

    CONSTRAINT chk_llm_checks_status
        CHECK (
            status IN (
                'queued',
                'processing',
                'completed',
                'failed'
            )
        ),

    CONSTRAINT chk_llm_checks_json_arrays
        CHECK (
            jsonb_typeof(issues) = 'array'
            AND jsonb_typeof(recommendations) = 'array'
        ),

    CONSTRAINT chk_llm_checks_completion_data
        CHECK (
            (
                status = 'completed'
                AND is_complete = TRUE
                AND completed_at IS NOT NULL
            )
            OR
            (
                status <> 'completed'
            )
        )
);

CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,

    actor_user_id UUID,

    action VARCHAR(64) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    entity_id UUID,

    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_address INET,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_audit_log_actor
        FOREIGN KEY (actor_user_id)
        REFERENCES users(id)
        ON DELETE SET NULL,

    CONSTRAINT chk_audit_log_action_not_empty
        CHECK (length(trim(action)) > 0),

    CONSTRAINT chk_audit_log_entity_type_not_empty
        CHECK (length(trim(entity_type)) > 0),

    CONSTRAINT chk_audit_log_details_object
        CHECK (jsonb_typeof(details) = 'object')
);

-- Индексы для проверки принадлежности объектов пользователям
CREATE INDEX idx_applications_applicant_id
    ON applications (applicant_id);

CREATE INDEX idx_documents_application_id
    ON documents (application_id);

CREATE INDEX idx_documents_uploaded_by
    ON documents (uploaded_by);

CREATE INDEX idx_llm_checks_application_id
    ON llm_checks (application_id);

CREATE INDEX idx_llm_checks_requested_by
    ON llm_checks (requested_by);

-- Индексы для фильтрации заявок
CREATE INDEX idx_applications_status
    ON applications (status);

CREATE INDEX idx_applications_support_type
    ON applications (support_type);

CREATE INDEX idx_applications_academic_year
    ON applications (academic_year);

CREATE INDEX idx_applications_created_at
    ON applications (created_at);

CREATE INDEX idx_applications_status_created_at
    ON applications (status, created_at);

-- Индексы для административных операций
CREATE INDEX idx_applications_reviewed_by
    ON applications (reviewed_by);

CREATE INDEX idx_users_department_id
    ON users (department_id);

CREATE INDEX idx_users_role
    ON users (role);

-- Индексы для обработки проверок языковой моделью и аудита
CREATE INDEX idx_llm_checks_status_created_at
    ON llm_checks (status, created_at);

CREATE INDEX idx_audit_log_actor_user_id
    ON audit_log (actor_user_id);

CREATE INDEX idx_audit_log_entity
    ON audit_log (entity_type, entity_id);

CREATE INDEX idx_audit_log_occurred_at
    ON audit_log (occurred_at);
